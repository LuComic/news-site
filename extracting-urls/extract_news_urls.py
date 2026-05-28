#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import ssl
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import datetime, timezone
from html import unescape
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import parse_qsl, urlencode, urljoin, urlparse, urlunparse
from urllib.request import Request, urlopen

USER_AGENT = "PublicSectorNewsUrlExtractor/0.1 (+contact@example.com)"
ARTICLE_PATH_RE = re.compile(
    r"/(uudised|uudis|news|pressiteated|pressiteade|press-release|press|teated)/[^/?#]{8,}",
    re.I,
)
DATED_PATH_RE = re.compile(r"/20\d{2}([/-]\d{1,2}){1,2}|/20\d{2}/", re.I)
SKIP_EXTENSIONS = (".pdf", ".doc", ".docx", ".xls", ".xlsx", ".zip", ".jpg", ".png")


@dataclass
class RouteContext:
    source_domain: str
    source_name: str
    route_url: str
    route_type: str
    source: dict[str, Any]
    route: dict[str, Any]


class LinkParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.links: list[tuple[str, str]] = []
        self._href: str | None = None
        self._parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() == "a":
            attrs_dict = {k.lower(): v for k, v in attrs}
            self._href = attrs_dict.get("href")
            self._parts = []

    def handle_data(self, data: str) -> None:
        if self._href:
            self._parts.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() == "a" and self._href:
            title = clean_text(" ".join(self._parts))
            self.links.append((self._href, title))
            self._href = None
            self._parts = []


def now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def clean_text(value: str) -> str:
    return re.sub(r"\s+", " ", unescape(value or "")).strip()


def source_base_domain(url: str) -> str:
    return urlparse(url).netloc.lower().removeprefix("www.")


def normalize_url(url: str, base: str | None = None) -> str | None:
    if not url:
        return None
    absolute = urljoin(base, url.strip()) if base else url.strip()
    parsed = urlparse(absolute)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return None
    path = parsed.path.rstrip("/") or "/"
    if path.lower().endswith(SKIP_EXTENSIONS):
        return None
    query = urlencode(
        sorted(parse_qsl(parsed.query, keep_blank_values=True)), doseq=True
    )
    return urlunparse((parsed.scheme, parsed.netloc.lower(), path, "", query, ""))


def looks_like_article(url: str, title: str = "") -> bool:
    parsed = urlparse(url)
    lowered = f"{parsed.path} {title}".lower()
    if any(term in lowered for term in ("kontakt", "privacy", "privaatsus", "sitemap")):
        return False
    return bool(
        ARTICLE_PATH_RE.search(parsed.path) or DATED_PATH_RE.search(parsed.path)
    )


def fetch(url: str, timeout: int = 25) -> tuple[str, str, str]:
    context = None
    try:
        import certifi

        context = ssl.create_default_context(cafile=certifi.where())
    except Exception:
        context = ssl.create_default_context()
    req = Request(url, headers={"User-Agent": USER_AGENT, "Accept": "*/*"})
    with urlopen(req, timeout=timeout, context=context) as response:
        final_url = response.geturl()
        content_type = response.headers.get("Content-Type", "")
        charset = response.headers.get_content_charset() or "utf-8"
        body = response.read().decode(charset, errors="replace")
        return final_url, content_type, body


def parse_feed(xml_text: str, route_url: str) -> Iterable[dict[str, str]]:
    namespaces = {
        "atom": "http://www.w3.org/2005/Atom",
        "dc": "http://purl.org/dc/elements/1.1/",
    }
    try:
        root = ET.fromstring(xml_text.encode("utf-8"))
    except ET.ParseError:
        return []
    found: list[dict[str, str]] = []
    for node in list(root.findall(".//item")) + list(
        root.findall(".//atom:entry", namespaces)
    ):
        title = clean_text(
            node.findtext("title")
            or node.findtext("atom:title", namespaces=namespaces)
            or ""
        )
        link = clean_text(node.findtext("link") or "")
        if not link:
            atom_link = node.find("atom:link", namespaces)
            link = atom_link.attrib.get("href", "") if atom_link is not None else ""
        published = clean_text(
            node.findtext("pubDate")
            or node.findtext("atom:published", namespaces=namespaces)
            or node.findtext("atom:updated", namespaces=namespaces)
            or node.findtext("dc:date", namespaces=namespaces)
            or ""
        )
        normalized = normalize_url(link, route_url)
        if normalized:
            found.append({"url": normalized, "title": title, "published_at": published})
    return found


def parse_html(
    html: str, route_url: str, route_domain: str
) -> Iterable[dict[str, str]]:
    parser = LinkParser()
    parser.feed(html)
    found: list[dict[str, str]] = []
    for href, title in parser.links:
        normalized = normalize_url(href, route_url)
        if not normalized or source_base_domain(normalized) != route_domain:
            continue
        if looks_like_article(normalized, title):
            found.append({"url": normalized, "title": title, "published_at": ""})
    return found


def walk_json_links(
    value: Any, route_url: str, route_domain: str
) -> Iterable[dict[str, str]]:
    found: list[dict[str, str]] = []
    if isinstance(value, dict):
        possible_url = (
            value.get("url")
            or value.get("link")
            or value.get("path")
            or value.get("href")
        )
        title = clean_text(
            str(value.get("title") or value.get("label") or value.get("name") or "")
        )
        if isinstance(possible_url, str):
            normalized = normalize_url(possible_url, route_url)
            if (
                normalized
                and source_base_domain(normalized) == route_domain
                and looks_like_article(normalized, title)
            ):
                found.append(
                    {
                        "url": normalized,
                        "title": title,
                        "published_at": clean_text(
                            str(value.get("created") or value.get("date") or "")
                        ),
                    }
                )
        for child in value.values():
            found.extend(walk_json_links(child, route_url, route_domain))
    elif isinstance(value, list):
        for child in value:
            found.extend(walk_json_links(child, route_url, route_domain))
    return found


def vportal_api_candidates(route_url: str) -> list[str]:
    parsed = urlparse(route_url)
    if "/otsing" not in parsed.path:
        return []
    query = dict(parse_qsl(parsed.query, keep_blank_values=True))
    query.setdefault("_format", "json")
    return [
        urlunparse(
            (parsed.scheme, parsed.netloc, parsed.path, "", urlencode(query), "")
        )
    ]


def discover_route(ctx: RouteContext, timeout: int) -> Iterable[dict[str, Any]]:
    route_domain = source_base_domain(ctx.route_url)
    candidates = [ctx.route_url] + vportal_api_candidates(ctx.route_url)
    seen_candidate_urls: set[str] = set()
    for candidate in candidates:
        if candidate in seen_candidate_urls:
            continue
        seen_candidate_urls.add(candidate)
        try:
            final_url, content_type, body = fetch(candidate, timeout=timeout)
        except Exception as exc:
            yield {"_error": str(exc), "_candidate": candidate}
            continue
        final_domain = source_base_domain(final_url)
        if (
            final_domain != route_domain
            or urlparse(final_url).path in {"", "/"}
            and urlparse(ctx.route_url).path not in {"", "/"}
        ):
            yield {"_error": f"stale redirect to {final_url}", "_candidate": candidate}
            continue
        method = (
            "rss_feed"
            if "xml" in content_type or ctx.route_type in {"rss", "atom"}
            else "html_listing_links"
        )
        items: Iterable[dict[str, str]]
        if "json" in content_type:
            try:
                items = walk_json_links(json.loads(body), final_url, route_domain)
                method = (
                    "vportal_search_api" if "/otsing" in ctx.route_url else "json_api"
                )
            except json.JSONDecodeError:
                items = []
        elif "xml" in content_type or ctx.route_type in {"rss", "atom"}:
            items = parse_feed(body, final_url)
        else:
            items = parse_html(body, final_url, route_domain)
        for item in items:
            yield {
                "url": item["url"],
                "source_domain": ctx.source_domain,
                "source_name": ctx.source_name,
                "route_url": ctx.route_url,
                "route_type": ctx.route_type,
                "discovered_title": item.get("title") or None,
                "discovered_published_at": item.get("published_at") or None,
                "discovered_at": now_iso(),
                "discovery_method": method,
            }


def iter_route_contexts(data: dict[str, Any]) -> Iterable[RouteContext]:
    for source in data.get("sources", []):
        organization = source.get("organization") or {}
        for route in source.get("articles_news_routes", []):
            yield RouteContext(
                source_domain=source.get("domain")
                or source_base_domain(source.get("website", "")),
                source_name=organization.get("name") or source.get("domain") or "",
                route_url=route["url"],
                route_type=route.get("route_type")
                or route.get("access_method")
                or "html",
                source=source,
                route=route,
            )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Extract article/news URLs from discovered public-sector routes."
    )
    parser.add_argument(
        "--sources", default="finding-sources/public_sector_sources.json"
    )
    parser.add_argument("--output", default="extracting-urls/news_urls.json")
    parser.add_argument("--errors", default="extracting-urls/errors.json")
    parser.add_argument("--timeout", type=int, default=25)
    parser.add_argument("--delay", type=float, default=0.35)
    args = parser.parse_args()

    data = json.loads(Path(args.sources).read_text(encoding="utf-8"))
    errors_path = Path(args.errors)
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    errors_path.parent.mkdir(parents=True, exist_ok=True)
    seen: set[str] = set()
    rows: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    count = 0
    for ctx in iter_route_contexts(data):
        for item in discover_route(ctx, args.timeout):
            if "_error" in item:
                errors.append(
                    {
                        "route_url": ctx.route_url,
                        "source_domain": ctx.source_domain,
                        "error_type": "route_discovery_failed",
                        "message": item["_error"],
                        "candidate_url": item.get("_candidate"),
                        "retrieved_at": now_iso(),
                    }
                )
                continue
            if item["url"] in seen:
                continue
            seen.add(item["url"])
            rows.append(item)
            count += 1
        time.sleep(args.delay)
    output_path.write_text(
        json.dumps(rows, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    errors_path.write_text(
        json.dumps(errors, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"Wrote {count} article URLs to {output_path}")
    print(f"Wrote {len(errors)} errors to {errors_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
