#!/usr/bin/env python3
from __future__ import annotations

import argparse
import importlib.util
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
EXTRACTING_NEWS = ROOT / "extracting-news"
sys.path.append(str(EXTRACTING_NEWS))

from common import (  # noqa: E402
    article_record,
    decode_body,
    error_record,
    fetch_url,
    load_url_rows,
    validation_error,
    write_markdown,
)

COMBINED_METHOD = "combined_fallback_extractor"


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not load module from {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


METHOD1 = load_module("method1_extract", EXTRACTING_NEWS / "method1" / "extract.py")
METHOD2 = load_module("method2_extract", EXTRACTING_NEWS / "method2" / "extract.py")


def run_command(args: list[str]) -> None:
    print("+", " ".join(args))
    subprocess.run(args, cwd=ROOT, check=True)


def run_source_finding(args: argparse.Namespace) -> None:
    if args.skip_source_finding:
        print("Skipping source finding")
        return
    command = [
        sys.executable,
        "finding-sources/discover_public_sector_sources.py",
        "--output",
        str(Path(args.sources_output)),
        "--max-domains",
        str(args.max_domains),
        "--max-routes-per-domain",
        str(args.max_routes_per_domain),
        "--timeout",
        str(args.timeout),
    ]
    if args.no_riha:
        command.append("--no-include-riha")
    if args.include_data_portal:
        command.append("--include-data-portal")
    run_command(command)


def run_url_extraction(args: argparse.Namespace) -> None:
    if args.skip_url_extraction:
        print("Skipping URL extraction")
        return
    command = [
        sys.executable,
        "extracting-urls/extract_news_urls.py",
        "--sources",
        args.sources_output,
        "--output",
        args.urls_output,
        "--errors",
        args.url_errors_output,
        "--timeout",
        str(args.timeout),
        "--delay",
        str(args.delay),
    ]
    run_command(command)


def trafilatura_extract(row: dict[str, Any], html: str, final_url: str):
    try:
        import trafilatura  # type: ignore[import-not-found]
    except ImportError as exc:
        raise RuntimeError("Install trafilatura to use this fallback") from exc
    raw = trafilatura.extract(
        html,
        url=final_url,
        output_format="json",
        with_metadata=True,
        include_links=True,
        include_images=True,
    )
    if not raw:
        raise RuntimeError("Trafilatura returned no extraction")
    data = json.loads(raw)
    return article_record(
        row,
        title=data.get("title"),
        lead=data.get("description"),
        body_text=data.get("text"),
        body_markdown=None,
        author=data.get("author"),
        published_at=data.get("date"),
        tags=[
            tag.strip()
            for tag in (data.get("categories") or "").split(",")
            if tag.strip()
        ],
        language=data.get("language") or "et",
        extraction_method="trafilatura",
        extraction_confidence="medium",
    )


def meta_content(soup, *names: str) -> str | None:
    from common import clean_text

    for name in names:
        node = soup.find("meta", attrs={"property": name}) or soup.find(
            "meta", attrs={"name": name}
        )
        if node and node.get("content"):
            return clean_text(node["content"])
    return None


def readability_extract(row: dict[str, Any], html: str, final_url: str):
    try:
        from bs4 import BeautifulSoup  # type: ignore[import-not-found]
        from readability import Document  # type: ignore[import-not-found]
    except ImportError as exc:
        raise RuntimeError(
            "Install beautifulsoup4 and readability-lxml to use this fallback"
        ) from exc

    original = BeautifulSoup(html, "html.parser")
    doc = Document(html)
    summary_html = doc.summary(html_partial=True)
    soup = BeautifulSoup(summary_html, "html.parser")
    body_text = soup.get_text("\n", strip=True)
    return article_record(
        row,
        title=doc.short_title() or meta_content(original, "og:title", "twitter:title"),
        lead=meta_content(original, "og:description", "description"),
        body_text=body_text,
        body_markdown=None,
        author=meta_content(original, "article:author", "author"),
        published_at=meta_content(original, "article:published_time", "date"),
        modified_at=meta_content(original, "article:modified_time"),
        images=[],
        links=[],
        extraction_method="readability_boilerplate_removal",
        extraction_confidence="medium",
    )


def is_feed_backed(row: dict[str, Any]) -> bool:
    route_url = row.get("route_url") or ""
    return bool(
        row.get("route_type") in {"rss", "atom"}
        or re.search(r"(rss|feed|atom)", route_url, re.I)
    )


def build_feed_index(
    rows: list[dict[str, Any]], timeout: int
) -> dict[str, dict[str, Any]]:
    feed_urls = sorted(
        row["route_url"]
        for row in rows
        if is_feed_backed(row) and isinstance(row.get("route_url"), str)
    )
    entries: dict[str, dict[str, Any]] = {}
    for feed_url in feed_urls:
        if not feed_url:
            continue
        try:
            _, content_type, body = fetch_url(feed_url, timeout)
            xml = decode_body(body, content_type)
            for entry in METHOD2.feed_entries(xml, feed_url):
                if entry.get("url"):
                    entries[METHOD2.normalize_match_url(entry["url"])] = entry
        except Exception:
            continue
    return entries


def feed_extract(row: dict[str, Any], feed_index: dict[str, dict[str, Any]]):
    entry = feed_index.get(METHOD2.normalize_match_url(row["url"]))
    if not entry:
        raise RuntimeError("No matching RSS/Atom entry found for article URL")
    body_text = METHOD2.html_to_text(entry["body_html"])
    confidence = "high" if entry["is_full"] and len(body_text) > 800 else "low"
    return article_record(
        row,
        title=entry["title"],
        lead=None if entry["is_full"] else body_text[:280],
        body_text=body_text,
        body_markdown=None,
        author=entry["author"],
        published_at=entry["published_at"],
        tags=entry["tags"],
        links=[entry["feed_url"]],
        extraction_method="feed_based_full_content",
        extraction_confidence=confidence,
    )


def accept_record(record: dict[str, Any]) -> tuple[bool, str | None]:
    problem = validation_error(record)
    if (
        problem == "body_too_short"
        and record.get("extraction_method") == "feed_based_full_content"
        and record.get("extraction_confidence") == "low"
        and len(record.get("body_text") or "") >= 120
    ):
        return True, None
    return problem is None, problem


def extract_one(
    row: dict[str, Any], feed_index: dict[str, dict[str, Any]], timeout: int
) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
    attempts: list[dict[str, Any]] = []
    html = ""
    final_url = row["url"]
    try:
        final_url, content_type, body = fetch_url(row["url"], timeout)
        html = decode_body(body, content_type)
    except Exception as exc:
        attempts.append(
            error_record(row, exc.__class__.__name__, str(exc), "fetch_article_html")
        )

    if html:
        for method_name, extractor in [
            ("deterministic_site_family_selectors", METHOD1.extract_with_selectors),
            ("trafilatura", trafilatura_extract),
            ("readability_boilerplate_removal", readability_extract),
        ]:
            try:
                record = extractor(row, html, final_url)
                ok, problem = accept_record(record)
                if ok:
                    record["fallback_chain"] = [
                        attempt["extraction_method"] for attempt in attempts
                    ] + [f"{method_name}:success"]
                    record["combined_extraction_method"] = COMBINED_METHOD
                    return record, attempts
                attempts.append(
                    error_record(
                        row,
                        problem or "validation_failed",
                        f"{method_name} validation failed: {problem}",
                        method_name,
                    )
                )
            except Exception as exc:
                attempts.append(
                    error_record(row, exc.__class__.__name__, str(exc), method_name)
                )

    if is_feed_backed(row):
        try:
            record = feed_extract(row, feed_index)
            ok, problem = accept_record(record)
            if ok:
                record["fallback_chain"] = [
                    attempt["extraction_method"] for attempt in attempts
                ] + ["feed_based_full_content:success"]
                record["combined_extraction_method"] = COMBINED_METHOD
                return record, attempts
            attempts.append(
                error_record(
                    row,
                    problem or "validation_failed",
                    f"feed_based_full_content validation failed: {problem}",
                    "feed_based_full_content",
                )
            )
        except Exception as exc:
            attempts.append(
                error_record(
                    row, exc.__class__.__name__, str(exc), "feed_based_full_content"
                )
            )

    return None, attempts


def write_final_output(
    records: list[dict[str, Any]], errors: list[dict[str, Any]], output_dir: Path
) -> None:
    markdowns_dir = output_dir / "markdowns"
    output_dir.mkdir(parents=True, exist_ok=True)
    if markdowns_dir.exists():
        shutil.rmtree(markdowns_dir)
    markdowns_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "articles.json").write_text(
        json.dumps(records, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (output_dir / "errors.json").write_text(
        json.dumps(errors, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    for record in records:
        write_markdown(record, markdowns_dir)


def run_combined_extraction(args: argparse.Namespace) -> None:
    rows = load_url_rows(args.urls_output, args.limit)
    feed_index = build_feed_index(rows, args.timeout)
    records: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    for index, row in enumerate(rows, start=1):
        print(f"Extracting {index}/{len(rows)} {row['url']}")
        record, attempts = extract_one(row, feed_index, args.timeout)
        if record:
            records.append(record)
        else:
            errors.extend(attempts)
    write_final_output(records, errors, Path(args.output_dir))
    print(f"Wrote {len(records)} final articles to {args.output_dir}/articles.json")
    print(f"Wrote {len(errors)} extraction errors to {args.output_dir}/errors.json")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run the full public-sector news pipeline."
    )
    parser.add_argument("--output-dir", default="output")
    parser.add_argument(
        "--sources-output", default="finding-sources/public_sector_sources.json"
    )
    parser.add_argument("--urls-output", default="extracting-urls/news_urls.json")
    parser.add_argument("--url-errors-output", default="extracting-urls/errors.json")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--timeout", type=int, default=25)
    parser.add_argument("--delay", type=float, default=0.35)
    parser.add_argument("--max-domains", type=int, default=100)
    parser.add_argument("--max-routes-per-domain", type=int, default=50)
    parser.add_argument("--include-data-portal", action="store_true")
    parser.add_argument("--no-riha", action="store_true")
    parser.add_argument("--skip-source-finding", action="store_true")
    parser.add_argument("--skip-url-extraction", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    run_source_finding(args)
    run_url_extraction(args)
    run_combined_extraction(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
