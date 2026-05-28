from __future__ import annotations

import hashlib
import json
import re
import shutil
import ssl
from datetime import datetime, timezone
from html import unescape
from pathlib import Path
from typing import Any
from urllib.parse import urlparse
from urllib.request import Request, urlopen

USER_AGENT = "PublicSectorArticleExtractor/0.1 (+contact@example.com)"
BOILERPLATE_PHRASES = (
    "küpsiseid",
    "cookie",
    "nõustun",
    "avaleht",
    "juurdepääsetavus",
    "privaatsuspoliitika",
)


def now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def clean_text(value: str | None) -> str:
    return re.sub(r"\s+", " ", unescape(value or "")).strip()


def paragraph_text(value: str | None) -> str:
    lines = [clean_text(line) for line in re.split(r"[\r\n]+", value or "")]
    return "\n\n".join(line for line in lines if line)


def fetch_url(url: str, timeout: int = 30) -> tuple[str, str, bytes]:
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/125.0 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "et-EE,et;q=0.9,en;q=0.8",
        "Connection": "close",
    }
    try:
        import requests

        response = requests.get(url, headers=headers, timeout=timeout)
        response.raise_for_status()
        return (
            response.url,
            response.headers.get("Content-Type", ""),
            response.content,
        )
    except Exception:
        pass

    context = None
    try:
        import certifi

        context = ssl.create_default_context(cafile=certifi.where())
    except Exception:
        context = ssl.create_default_context()
    req = Request(
        url,
        headers=headers,
    )
    with urlopen(req, timeout=timeout, context=context) as response:
        return (
            response.geturl(),
            response.headers.get("Content-Type", ""),
            response.read(),
        )


def decode_body(body: bytes, content_type: str) -> str:
    match = re.search(r"charset=([^;]+)", content_type, re.I)
    charset = match.group(1).strip() if match else "utf-8"
    return body.decode(charset, errors="replace")


def load_url_rows(path: str | Path, limit: int | None = None) -> list[dict[str, Any]]:
    path = Path(path)
    if path.suffix == ".json":
        rows = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(rows, list):
            raise ValueError(f"Expected a JSON array in {path}")
        return rows[:limit] if limit is not None else rows

    rows: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                rows.append(json.loads(line))
                if limit is not None and len(rows) >= limit:
                    break
    return rows


def safe_slug(url: str, title: str | None = None) -> str:
    parsed = urlparse(url)
    stem = (title or parsed.path.rsplit("/", 1)[-1] or parsed.netloc).lower()
    stem = re.sub(r"[^a-z0-9]+", "-", stem).strip("-")[:70] or "article"
    digest = hashlib.sha1(url.encode("utf-8")).hexdigest()[:10]
    return f"{stem}-{digest}"


def markdown_escape_yaml(value: Any) -> str:
    if value is None:
        return "null"
    return json.dumps(value, ensure_ascii=False)


def article_record(
    url_row: dict[str, Any],
    *,
    title: str | None,
    lead: str | None,
    body_text: str | None,
    body_markdown: str | None,
    author: str | None = None,
    published_at: str | None = None,
    modified_at: str | None = None,
    tags: list[str] | None = None,
    language: str | None = "et",
    images: list[str] | None = None,
    links: list[str] | None = None,
    extraction_method: str,
    extraction_confidence: str,
    retrieved_at: str | None = None,
) -> dict[str, Any]:
    body_text = paragraph_text(body_text)
    title = clean_text(title) or clean_text(url_row.get("discovered_title")) or None
    lead = clean_text(lead) or None
    if not body_markdown and body_text:
        body_markdown = f"# {title}\n\n" if title else ""
        if lead:
            body_markdown += f"**{lead}**\n\n"
        body_markdown += body_text
    paragraphs = [p for p in re.split(r"\n{2,}", body_text or "") if p.strip()]
    return {
        "url": url_row["url"],
        "source_domain": url_row.get("source_domain"),
        "source_name": url_row.get("source_name"),
        "title": title,
        "lead": lead,
        "body_text": body_text,
        "body_markdown": body_markdown,
        "author": clean_text(author) or None,
        "published_at": published_at or url_row.get("discovered_published_at"),
        "modified_at": modified_at,
        "tags": tags or [],
        "language": language,
        "images": images or [],
        "links": links or [],
        "extraction_method": extraction_method,
        "extraction_confidence": extraction_confidence,
        "content_length_chars": len(body_text or ""),
        "paragraph_count": len(paragraphs),
        "retrieved_at": retrieved_at or now_iso(),
    }


def validation_error(record: dict[str, Any]) -> str | None:
    if not record.get("url"):
        return "missing_url"
    if not record.get("title"):
        return "missing_title"
    body = record.get("body_text") or ""
    if not body:
        return "empty_body"
    if len(body) < 280:
        return "body_too_short"
    lowered = body.lower()
    boilerplate_hits = sum(lowered.count(phrase) for phrase in BOILERPLATE_PHRASES)
    if boilerplate_hits and boilerplate_hits * 80 > len(body):
        return "boilerplate_dominant"
    if record.get("extraction_confidence") not in {"high", "medium", "low"}:
        return "invalid_confidence"
    return None


def error_record(
    url_row: dict[str, Any], error_type: str, message: str, method: str
) -> dict[str, Any]:
    return {
        "url": url_row.get("url"),
        "source_domain": url_row.get("source_domain"),
        "error_type": error_type,
        "message": message,
        "extraction_method": method,
        "retrieved_at": now_iso(),
    }


def write_markdown(record: dict[str, Any], output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / f"{safe_slug(record['url'], record.get('title'))}.md"
    frontmatter = {
        "title": record.get("title"),
        "source": record.get("source_name"),
        "source_domain": record.get("source_domain"),
        "url": record.get("url"),
        "published_at": record.get("published_at"),
        "author": record.get("author"),
        "language": record.get("language"),
        "tags": record.get("tags"),
        "extraction_method": record.get("extraction_method"),
        "extraction_confidence": record.get("extraction_confidence"),
        "retrieved_at": record.get("retrieved_at"),
    }
    yaml = "\n".join(
        f"{key}: {markdown_escape_yaml(value)}" for key, value in frontmatter.items()
    )
    path.write_text(
        f"---\n{yaml}\n---\n\n{record.get('body_markdown') or ''}\n", encoding="utf-8"
    )


def write_outputs(
    records: list[dict[str, Any]], errors: list[dict[str, Any]], output_dir: str | Path
) -> None:
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    markdown_dir = out / "markdown"
    if markdown_dir.exists():
        shutil.rmtree(markdown_dir)
    for stale_jsonl in (out / "articles.jsonl", out / "errors.jsonl"):
        if stale_jsonl.exists():
            stale_jsonl.unlink()
    for record in records:
        write_markdown(record, markdown_dir)
    (out / "articles.json").write_text(
        json.dumps(records, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (out / "errors.json").write_text(
        json.dumps(errors, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
