#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))
from common import (
    article_record,
    error_record,
    fetch_url,
    load_url_rows,
    validation_error,
    write_outputs,
)

METHOD = "trafilatura"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", default="extracting-urls/news_urls.json")
    parser.add_argument("--output-dir", default="extracting-news/method3/output")
    parser.add_argument("--timeout", type=int, default=30)
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args()
    records, errors = [], []
    try:
        import trafilatura  # type: ignore[import-not-found]
    except ImportError:
        rows = load_url_rows(args.input, args.limit)
        errors = [
            error_record(
                row, "missing_dependency", "Install trafilatura to run method3", METHOD
            )
            for row in rows
        ]
        write_outputs([], errors, args.output_dir)
        print(f"method3 wrote 0 articles and {len(errors)} errors")
        return 0
    for row in load_url_rows(args.input, args.limit):
        try:
            final_url, _, body = fetch_url(row["url"], args.timeout)
            html = body.decode("utf-8", errors="replace")
            raw = trafilatura.extract(
                html,
                url=final_url,
                output_format="json",
                with_metadata=True,
                include_links=True,
                include_images=True,
            )
            if not raw:
                errors.append(
                    error_record(
                        row, "empty_body", "Trafilatura returned no extraction", METHOD
                    )
                )
                continue
            data = json.loads(raw)
            record = article_record(
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
    print(f"method3 wrote {len(records)} articles and {len(errors)} errors")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
