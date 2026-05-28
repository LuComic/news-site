#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any

from run_pipeline import build_feed_index, extract_one

ROOT = Path(__file__).resolve().parent


def compact_attempts(attempts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "extraction_method": attempt.get("extraction_method"),
            "error_type": attempt.get("error_type"),
            "message": attempt.get("message"),
        }
        for attempt in attempts
    ]


def load_rows(path: Path, limit: int | None) -> list[dict[str, Any]]:
    rows = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(rows, list):
        raise ValueError(f"Expected a JSON array in {path}")
    return rows[:limit] if limit is not None else rows


def percentage(successes: int, total: int) -> float:
    return (successes / total * 100) if total else 0.0


def audit(args: argparse.Namespace) -> dict[str, Any]:
    rows = load_rows(Path(args.urls), args.limit)
    total = len(rows)
    print(f"Loaded {total} URLs from {args.urls}")

    feed_index = build_feed_index(rows, args.timeout)
    if feed_index:
        print(f"Built RSS/Atom index with {len(feed_index)} entries")

    successes: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    method_counts: Counter[str] = Counter()
    source_counts: Counter[str] = Counter()

    for index, row in enumerate(rows, start=1):
        url = row.get("url", "")
        print(f"[{index}/{total}] Checking {url}")
        record, attempts = extract_one(row, feed_index, args.timeout)

        if record:
            method = record.get("extraction_method") or "unknown"
            method_counts[method] += 1
            source_counts[row.get("source_domain") or "unknown"] += 1
            successes.append(
                {
                    "url": url,
                    "source_domain": row.get("source_domain"),
                    "title": record.get("title"),
                    "extraction_method": method,
                    "extraction_confidence": record.get("extraction_confidence"),
                    "content_length_chars": record.get("content_length_chars"),
                    "paragraph_count": record.get("paragraph_count"),
                    "fallback_chain": record.get("fallback_chain"),
                }
            )
            print(f"  SUCCESS {method} ({record.get('content_length_chars', 0)} chars)")
            continue

        last_attempt = attempts[-1] if attempts else {}
        errors.append(
            {
                "url": url,
                "source_domain": row.get("source_domain"),
                "last_error_type": last_attempt.get("error_type"),
                "last_message": last_attempt.get("message"),
                "attempts": compact_attempts(attempts),
            }
        )
        print(
            "  ERROR "
            f"{last_attempt.get('extraction_method', 'unknown')}: "
            f"{last_attempt.get('error_type', 'unknown')} - "
            f"{last_attempt.get('message', 'No extraction attempts recorded')}"
        )

    success_count = len(successes)
    error_count = len(errors)
    summary = {
        "urls_input": str(Path(args.urls)),
        "total_urls": total,
        "successful_extractions": success_count,
        "failed_extractions": error_count,
        "success_rate_percent": round(percentage(success_count, total), 2),
        "failure_rate_percent": round(percentage(error_count, total), 2),
        "successes_by_method": dict(method_counts.most_common()),
        "successes_by_source_domain": dict(source_counts.most_common()),
    }
    return {
        "summary": summary,
        "successes": successes,
        "errors": errors,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Audit how many discovered news URLs can be extracted without "
            "writing article markdown or article JSON outputs."
        )
    )
    parser.add_argument("--urls", default="extracting-urls/news_urls.json")
    parser.add_argument("--timeout", type=int, default=25)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument(
        "--report",
        default="output/extraction_audit.json",
        help="JSON audit report path. Stores summary, compact successes, and errors.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    result = audit(args)
    summary = result["summary"]

    report_path = Path(args.report)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(
        json.dumps(result, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print()
    print("Extraction audit summary")
    print(f"  Total URLs: {summary['total_urls']}")
    print(f"  Successes: {summary['successful_extractions']}")
    print(f"  Errors: {summary['failed_extractions']}")
    print(f"  Success rate: {summary['success_rate_percent']}%")
    print(f"  Failure rate: {summary['failure_rate_percent']}%")
    print(f"  Report: {report_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
