#!/usr/bin/env python3
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from urllib.parse import urljoin

sys.path.append(str(Path(__file__).resolve().parents[1]))
from common import (
    article_record,
    decode_body,
    error_record,
    fetch_url,
    load_url_rows,
    validation_error,
    write_outputs,
)

METHOD = "deterministic_site_family_selectors"
VPORTAL_DOMAINS = {
    "valitsus.ee",
    "fin.ee",
    "justdigi.ee",
    "kliimaministeerium.ee",
    "keskkonnaamet.ee",
    "konkurentsiamet.ee",
    "transpordiamet.ee",
}


def text_from_nodes(nodes) -> str:
    return "\n\n".join(
        node.get_text(" ", strip=True)
        for node in nodes
        if node.get_text(" ", strip=True)
    )


def meta_content(soup, *names: str) -> str | None:
    for name in names:
        node = soup.find("meta", attrs={"property": name}) or soup.find(
            "meta", attrs={"name": name}
        )
        if node and node.get("content"):
            return node["content"].strip()
    return None


def attr_str(value) -> str | None:
    return value if isinstance(value, str) else None


def extract_with_selectors(url_row, html: str, final_url: str):
    try:
        from bs4 import BeautifulSoup  # type: ignore[import-not-found]
    except ImportError as exc:
        raise RuntimeError("beautifulsoup4 is required for method1") from exc
    soup = BeautifulSoup(html, "html.parser")
    domain = (url_row.get("source_domain") or "").removeprefix("www.")
    title = lead = body = author = published = modified = None
    tags: list[str] = []
    images: list[str] = []
    links: list[str] = []
    confidence = "medium"

    if domain in VPORTAL_DOMAINS:
        article = soup.select_one("article.node--type-news") or soup.select_one("main")
        title_node = soup.select_one("h1") or soup.select_one(".page-title")
        lead_node = soup.select_one(".field--name-field-lead-text")
        body_nodes = soup.select(
            ".field--name-field-news-components .field--name-field-text-section-content"
        )
        if not body_nodes:
            body_nodes = soup.select(
                ".field--name-body, .field--name-field-text-section-content"
            )
        author_node = soup.select_one(".field--name-field-news-authors")
        date_node = soup.select_one(
            ".card-text.vp-date time, .card-text.vp-date, time[datetime]"
        )
        title = title_node.get_text(" ", strip=True) if title_node else None
        lead = lead_node.get_text(" ", strip=True) if lead_node else None
        body = text_from_nodes(body_nodes) or (
            article.get_text("\n", strip=True) if article else ""
        )
        author = author_node.get_text(" ", strip=True) if author_node else None
        published = (
            attr_str(date_node.get("datetime"))
            if date_node and date_node.has_attr("datetime")
            else (date_node.get_text(" ", strip=True) if date_node else None)
        )
        tags = [
            node.get_text(" ", strip=True)
            for node in soup.select(
                ".field--name-field-keywords a, .field--name-field-keywords .field__item"
            )
        ]
        confidence = "high" if body_nodes else "medium"
    elif domain in {"politsei.ee", "rescue.ee"}:
        main = soup.select_one("main#maincontent")
        title_node = soup.select_one(
            "main#maincontent .content h1, main#maincontent h1"
        )
        time_node = soup.select_one("main#maincontent time[datetime]")
        body_node = soup.select_one("main#maincontent section.componentized") or main
        title = title_node.get_text(" ", strip=True) if title_node else None
        body = body_node.get_text("\n", strip=True) if body_node else ""
        published = attr_str(time_node.get("datetime")) if time_node else None
        confidence = "high" if body_node else "medium"
    elif domain == "stat.ee":
        article = soup.select_one("article.node--type-article") or soup.select_one(
            "main"
        )
        title_node = soup.select_one("h1.page-title, h1")
        lead_node = soup.select_one(".field--name-field-summary-news")
        body_node = soup.select_one(".field--name-body")
        title = title_node.get_text(" ", strip=True) if title_node else None
        lead = lead_node.get_text(" ", strip=True) if lead_node else None
        body = (
            body_node.get_text("\n", strip=True)
            if body_node
            else (article.get_text("\n", strip=True) if article else "")
        )
        confidence = "high" if body_node else "medium"
    else:
        article = soup.select_one("article.post, article, main")
        title_node = soup.select_one("article.post h1, h1.entry-title, h1")
        body_node = soup.select_one(".entry-content, article .content, article, main")
        title = (
            title_node.get_text(" ", strip=True)
            if title_node
            else meta_content(soup, "og:title")
        )
        body = body_node.get_text("\n", strip=True) if body_node else ""
        confidence = "medium"

    title = title or meta_content(soup, "og:title", "twitter:title")
    published = published or meta_content(soup, "article:published_time", "date")
    modified = modified or meta_content(soup, "article:modified_time")
    for img in soup.select("article img[src], main img[src]"):
        src = urljoin(final_url, attr_str(img.get("src")))
        if src not in images:
            images.append(src)
    for link in soup.select("article a[href], main a[href]"):
        href = urljoin(final_url, attr_str(link.get("href")))
        if href not in links:
            links.append(href)
    body = re.sub(r"\n{3,}", "\n\n", body or "")
    return article_record(
        url_row,
        title=title,
        lead=lead,
        body_text=body,
        body_markdown=None,
        author=author,
        published_at=published,
        modified_at=modified,
        tags=tags,
        images=images,
        links=links,
        extraction_method=METHOD,
        extraction_confidence=confidence,
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", default="extracting-urls/news_urls.json")
    parser.add_argument("--output-dir", default="extracting-news/method1/output")
    parser.add_argument("--timeout", type=int, default=30)
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args()
    records, errors = [], []
    for row in load_url_rows(args.input, args.limit):
        try:
            final_url, content_type, body = fetch_url(row["url"], args.timeout)
            record = extract_with_selectors(
                row, decode_body(body, content_type), final_url
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
    print(f"method1 wrote {len(records)} articles and {len(errors)} errors")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
