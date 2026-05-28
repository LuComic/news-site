#!/usr/bin/env python3
from __future__ import annotations

import argparse
import re
import sys
import xml.etree.ElementTree as ET
from html import unescape
from pathlib import Path

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

METHOD = "feed_based_full_content"


def normalize_match_url(url: str) -> str:
    return re.sub(r"/+$", "", url.split("#", 1)[0])


def html_to_text(html: str) -> str:
    try:
        from bs4 import BeautifulSoup  # type: ignore[import-not-found]

        soup = BeautifulSoup(html, "html.parser")
        return soup.get_text("\n", strip=True)
    except ImportError:
        return re.sub(r"<[^>]+>", " ", unescape(html))


def feed_entries(xml_text: str, feed_url: str) -> list[dict]:
    ns = {
        "atom": "http://www.w3.org/2005/Atom",
        "content": "http://purl.org/rss/1.0/modules/content/",
        "dc": "http://purl.org/dc/elements/1.1/",
    }
    root = ET.fromstring(xml_text.encode("utf-8"))
    entries = []
    for node in list(root.findall(".//item")) + list(root.findall(".//atom:entry", ns)):
        link = clean_text(node.findtext("link") or "")
        if not link:
            atom_link = node.find("atom:link", ns)
            link = atom_link.attrib.get("href", "") if atom_link is not None else ""
        content = (
            node.findtext("content:encoded", namespaces=ns)
            or node.findtext("atom:content", namespaces=ns)
            or ""
        )
        summary = (
            node.findtext("description")
            or node.findtext("atom:summary", namespaces=ns)
            or ""
        )
        categories = [
            clean_text(cat.text or cat.attrib.get("term", ""))
            for cat in node.findall("category") + node.findall("atom:category", ns)
        ]
        entries.append(
            {
                "url": normalize_match_url(link),
                "title": clean_text(
                    node.findtext("title")
                    or node.findtext("atom:title", namespaces=ns)
                    or ""
                ),
                "body_html": content or summary,
                "is_full": bool(content and len(content) > len(summary)),
                "published_at": clean_text(
                    node.findtext("pubDate")
                    or node.findtext("atom:published", namespaces=ns)
                    or node.findtext("atom:updated", namespaces=ns)
                    or ""
                ),
                "author": clean_text(
                    node.findtext("dc:creator", namespaces=ns)
                    or node.findtext("author")
                    or ""
                ),
                "tags": [tag for tag in categories if tag],
                "feed_url": feed_url,
            }
        )
    return entries


def collect_feeds(rows):
    feeds = {}
    for row in rows:
        route_url = row.get("route_url")
        if route_url and (
            row.get("route_type") in {"rss", "atom"}
            or re.search(r"(rss|feed|atom)", route_url, re.I)
        ):
            feeds[route_url] = None
    return feeds


def is_feed_backed(row):
    route_url = row.get("route_url") or ""
    return row.get("route_type") in {"rss", "atom"} or re.search(
        r"(rss|feed|atom)", route_url, re.I
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", default="extracting-urls/news_urls.json")
    parser.add_argument("--output-dir", default="extracting-news/method2/output")
    parser.add_argument("--timeout", type=int, default=30)
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args()
    all_rows = load_url_rows(args.input)
    rows = [row for row in all_rows if is_feed_backed(row)]
    if args.limit is not None:
        rows = rows[: args.limit]
    errors, records = [], []
    entry_by_url = {}
    for feed_url in collect_feeds(rows):
        try:
            _, content_type, body = fetch_url(feed_url, args.timeout)
            for entry in feed_entries(decode_body(body, content_type), feed_url):
                if entry["url"]:
                    entry_by_url[entry["url"]] = entry
        except Exception:
            continue
    for row in rows:
        entry = entry_by_url.get(normalize_match_url(row["url"]))
        if not entry:
            errors.append(
                error_record(
                    row,
                    "feed_entry_not_found",
                    "No matching RSS/Atom entry found for article URL",
                    METHOD,
                )
            )
            continue
        body_text = html_to_text(entry["body_html"])
        confidence = "high" if entry["is_full"] and len(body_text) > 800 else "low"
        record = article_record(
            row,
            title=entry["title"],
            lead=None if entry["is_full"] else body_text[:280],
            body_text=body_text,
            body_markdown=None,
            author=entry["author"],
            published_at=entry["published_at"],
            tags=entry["tags"],
            links=[entry["feed_url"]],
            extraction_method=METHOD,
            extraction_confidence=confidence,
        )
        problem = validation_error(record)
        if (
            problem == "body_too_short"
            and confidence == "low"
            and record.get("body_text")
            and len(record["body_text"]) >= 120
        ):
            problem = None
        if problem:
            errors.append(
                error_record(row, problem, f"Validation failed: {problem}", METHOD)
            )
        else:
            records.append(record)
    write_outputs(records, errors, args.output_dir)
    print(f"method2 wrote {len(records)} articles and {len(errors)} errors")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
