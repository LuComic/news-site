#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from urllib.parse import urljoin

sys.path.append(str(Path(__file__).resolve().parents[1]))
from common import (
    article_record,
    clean_text,
    decode_body,
    error_record,
    fetch_url,
    load_url_rows,
    validation_error,
    write_outputs,
)

METHOD = "readability_boilerplate_removal"


def meta_content(soup, *names):
    for name in names:
        node = soup.find("meta", attrs={"property": name}) or soup.find(
            "meta", attrs={"name": name}
        )
        if node and node.get("content"):
            return clean_text(node["content"])
    return None


def attr_str(value) -> str | None:
    return value if isinstance(value, str) else None


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", default="extracting-urls/news_urls.json")
    parser.add_argument("--output-dir", default="extracting-news/method4/output")
    parser.add_argument("--timeout", type=int, default=30)
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args()
    records, errors = [], []
    try:
        from bs4 import BeautifulSoup  # type: ignore[import-not-found]
        from readability import Document  # type: ignore[import-not-found]
    except ImportError:
        rows = load_url_rows(args.input, args.limit)
        errors = [
            error_record(
                row,
                "missing_dependency",
                "Install beautifulsoup4 and readability-lxml to run method4",
                METHOD,
            )
            for row in rows
        ]
        write_outputs([], errors, args.output_dir)
        print(f"method4 wrote 0 articles and {len(errors)} errors")
        return 0
    for row in load_url_rows(args.input, args.limit):
        try:
            final_url, content_type, body = fetch_url(row["url"], args.timeout)
            html = decode_body(body, content_type)
            original = BeautifulSoup(html, "html.parser")
            doc = Document(html)
            title = clean_text(doc.short_title()) or meta_content(
                original, "og:title", "twitter:title"
            )
            summary_html = doc.summary(html_partial=True)
            soup = BeautifulSoup(summary_html, "html.parser")
            body_text = soup.get_text("\n", strip=True)
            images = [
                urljoin(final_url, attr_str(img.get("src")))
                for img in soup.select("img[src]")
            ]
            links = [
                urljoin(final_url, attr_str(a.get("href")))
                for a in soup.select("a[href]")
            ]
            record = article_record(
                row,
                title=title,
                lead=meta_content(original, "og:description", "description"),
                body_text=body_text,
                body_markdown=None,
                author=meta_content(original, "article:author", "author"),
                published_at=meta_content(original, "article:published_time", "date"),
                modified_at=meta_content(original, "article:modified_time"),
                tags=[],
                images=list(dict.fromkeys(images)),
                links=list(dict.fromkeys(links)),
                extraction_method=METHOD,
                extraction_confidence="medium",
            )
            problem = validation_error(record)
            if problem:
                errors.append(
                    error_record(row, problem, f"Validation failed: {problem}", METHOD)
                )
            else:
                records.append(record)
        except Exception as exc:
            errors.append(error_record(row, exc.__class__.__name__, str(exc), METHOD))
    write_outputs(records, errors, args.output_dir)
    print(f"method4 wrote {len(records)} articles and {len(errors)} errors")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
