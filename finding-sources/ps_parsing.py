from __future__ import annotations

import hashlib
import re
import xml.etree.ElementTree as ET
from html.parser import HTMLParser
from typing import Dict, Iterable, List, Optional, Tuple
from urllib.parse import urljoin, urlparse, urlunparse

from ps_models import BAD_DOMAINS, KEYWORDS, LatestItem


class PageParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.links: List[Tuple[str, str]] = []
        self.feed_links: List[str] = []
        self.title = ""
        self._current_href: Optional[str] = None
        self._text_parts: List[str] = []
        self._in_title = False
        self._title_parts: List[str] = []

    def handle_starttag(self, tag: str, attrs: List[Tuple[str, Optional[str]]]) -> None:
        attrs_dict = {k.lower(): v for k, v in attrs}
        if tag.lower() == "a":
            self._current_href = attrs_dict.get("href")
            self._text_parts = []
        elif tag.lower() == "link":
            rel = (attrs_dict.get("rel") or "").lower()
            typ = (attrs_dict.get("type") or "").lower()
            href = attrs_dict.get("href")
            if href and ("alternate" in rel or "rss" in typ or "atom" in typ):
                self.feed_links.append(href)
        elif tag.lower() == "title":
            self._in_title = True
            self._title_parts = []

    def handle_data(self, data: str) -> None:
        if self._current_href:
            self._text_parts.append(data)
        if self._in_title:
            self._title_parts.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() == "a" and self._current_href:
            text = " ".join(part.strip() for part in self._text_parts if part.strip())
            self.links.append((self._current_href, text))
            self._current_href = None
            self._text_parts = []
        elif tag.lower() == "title":
            self.title = " ".join(
                part.strip() for part in self._title_parts if part.strip()
            )
            self._in_title = False


def unique_ordered(values: Iterable[str]) -> List[str]:
    return list(dict.fromkeys(values))


def content_signature(text: str) -> str:
    normalized = re.sub(r"\s+", " ", text).strip()
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def normalize_url(url: str, base: Optional[str] = None) -> Optional[str]:
    if not url:
        return None
    url = url.strip()
    if base:
        url = urljoin(base, url)
    if not re.match(r"^https?://", url):
        return None
    parsed = urlparse(url)
    host = parsed.netloc.lower()
    if not host or any(bad in host for bad in BAD_DOMAINS):
        return None
    return urlunparse(
        (parsed.scheme, host, parsed.path.rstrip("/") or "/", "", parsed.query, "")
    )


def domain(url: str) -> str:
    return urlparse(url).netloc.lower().removeprefix("www.")


def base_url(url: str) -> str:
    parsed = urlparse(url)
    return f"{parsed.scheme}://{parsed.netloc}"


def classify_route(url: str, title: str = "", anchor_text: str = "") -> str:
    value = f"{url} {title} {anchor_text}".lower()
    rules = [
        ("rss", ["rss", "feed"]),
        ("atom", ["atom"]),
        ("api", ["api", "jsonapi", "wp-json", "graphql"]),
        ("sitemap", ["sitemap"]),
        ("press_releases", ["pressiteade", "pressiteated", "press release", "press"]),
        ("news", ["uudised", "uudis", "news", "aktuaalne"]),
        ("public_notices", ["teadaanded", "notices", "announcements", "ametlikud"]),
        ("procurement", ["hanked", "riigihanked", "procurement", "tenders"]),
        ("documents", ["dokumendiregister", "dokumendid", "documents"]),
        ("consultations", ["kaasamine", "consultation", "avalikud arutelud"]),
        ("planning", ["planeeringud", "planning"]),
        ("grants", ["toetused", "grants"]),
        ("contact", ["kontakt", "contact"]),
    ]
    for route_type, keywords in rules:
        if any(keyword in value for keyword in keywords):
            return route_type
    return "unknown"


def access_method(url: str, status: Optional[int]) -> str:
    lowered = url.lower()
    if "rss" in lowered or "feed" in lowered:
        return "rss"
    if "atom" in lowered:
        return "atom"
    if "sitemap" in lowered:
        return "sitemap"
    if any(text in lowered for text in ["api", "jsonapi", "wp-json", "graphql"]):
        if status == 200:
            return "api_public"
        if status in (401, 403):
            return "api_restricted"
        return "unknown"
    if "robots.txt" in lowered:
        return "robots"
    return "html"


def keyword_hits(*values: str) -> List[str]:
    combined = " ".join(values).lower()
    return [keyword for keyword in KEYWORDS if keyword in combined][:10]


def looks_like_article_item(url: str, text: str) -> bool:
    lowered = f"{url} {text}".lower()
    if len(text.strip()) < 8:
        return False
    bad_terms = (
        "kontakt",
        "contact",
        "toole",
        "tööle",
        "praktika",
        "isikuandmete",
        "organisatsioon",
        "ministeeriumist",
    )
    if any(term in lowered for term in bad_terms):
        return False
    parsed_path = urlparse(url).path.lower()
    article_path = bool(
        re.search(
            r"/(uudised|news|pressiteated|press-release|press)/[^/?#]{12,}", parsed_path
        )
    )
    dated_path = bool(re.search(r"/20\d{2}/\d{1,2}(/|-)", parsed_path)) or bool(
        re.search(r"/20\d{2}-\d{1,2}-\d{1,2}", parsed_path)
    )
    return article_path or dated_path


def extract_html_items(html: str, route_url: str, limit: int = 8) -> List[LatestItem]:
    parser = PageParser()
    try:
        parser.feed(html)
    except Exception:
        return []
    route_domain = domain(route_url)
    items: List[LatestItem] = []
    seen = set()
    for href, text in parser.links:
        absolute = normalize_url(href, route_url)
        if not absolute or domain(absolute) != route_domain:
            continue
        if absolute in seen or absolute == route_url:
            continue
        if not looks_like_article_item(absolute, text):
            continue
        seen.add(absolute)
        items.append(LatestItem(title=text[:180], url=absolute))
        if len(items) >= limit:
            break
    return items


def extract_feed_items(xml_text: str, limit: int = 8) -> List[LatestItem]:
    items: List[LatestItem] = []
    try:
        root = ET.fromstring(xml_text.encode("utf-8"))
    except Exception:
        return items
    namespaces: Dict[str, str] = {
        "atom": "http://www.w3.org/2005/Atom",
        "dc": "http://purl.org/dc/elements/1.1/",
    }
    rss_items = root.findall(".//item")
    atom_items = root.findall(".//atom:entry", namespaces)
    for node in rss_items + atom_items:
        title = (
            node.findtext("title")
            or node.findtext("atom:title", namespaces=namespaces)
            or ""
        )
        link = (node.findtext("link") or "").strip()
        if not link:
            atom_link = node.find("atom:link", namespaces)
            link = atom_link.attrib.get("href", "") if atom_link is not None else ""
        published = (
            node.findtext("pubDate")
            or node.findtext("atom:updated", namespaces=namespaces)
            or node.findtext("atom:published", namespaces=namespaces)
            or node.findtext("dc:date", namespaces=namespaces)
            or ""
        ).strip()
        if title and link:
            items.append(
                LatestItem(title=title[:180], url=link, published_at=published)
            )
        if len(items) >= limit:
            break
    return items


def parse_page(html: str) -> PageParser:
    parser = PageParser()
    parser.feed(html)
    return parser
