from __future__ import annotations

import gzip
import hashlib
import json
import logging
import os
import re
import secrets
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set, Tuple
from urllib.parse import urljoin, urlparse

import requests
from ps_http import HttpClient
from ps_models import (
    ARTICLE_ROUTE_TYPES,
    CMS_PATHS,
    CURATED_PUBLIC_SECTOR_SOURCES,
    INVALID_CONTENT_TYPES,
    KEYWORDS,
    KNOWN_PATHS,
    SCRIPT_VERSION,
    SITEMAP_PATHS,
    SOFT_404_PATTERNS,
    Config,
    LatestItem,
    OrganizationCandidate,
    RouteCandidate,
    SourceRecord,
)
from ps_parsing import (
    access_method,
    base_url,
    classify_route,
    content_signature,
    domain,
    extract_feed_items,
    extract_html_items,
    keyword_hits,
    normalize_url,
    parse_page,
)

VALID_ROUTE_STATUSES = {200, 401, 403}
BAD_ROUTE_TERMS = (
    "kontakt",
    "contact",
    "toole",
    "tööle",
    "praktika",
    "isikuandmete",
    "organisatsioon",
    "ministeeriumist",
    "el-ja-rahvusvaheline",
    "pressikontakt",
    "kommunikatsiooniburoo",
)


class SourceDiscovery:
    def __init__(self, cfg: Config):
        self.cfg = cfg
        self.http = HttpClient(cfg)
        self.orgs: Dict[str, OrganizationCandidate] = {}
        self.records: Dict[str, SourceRecord] = {}
        self.fallback_signatures: Dict[str, str] = {}
        self.generated_at = datetime.now(timezone.utc).isoformat()
        self.start_time = time.time()

    def progress(self, message: str) -> None:
        elapsed = time.time() - self.start_time
        print(f"[{elapsed:8.1f}s] {message}", flush=True)

    def key(self, name: str) -> str:
        return (
            re.sub(r"\W+", " ", name.lower()).strip()
            or hashlib.md5(name.encode()).hexdigest()
        )

    def add_org(self, org: OrganizationCandidate) -> None:
        key = self.key(org.name)
        old = self.orgs.get(key)
        if old:
            old.discovered_from |= org.discovered_from
            old.raw_urls |= org.raw_urls
            old.registry_code = old.registry_code or org.registry_code
            old.type = old.type or org.type
            old.parent = old.parent or org.parent
            old.email = old.email or org.email
            old.address = old.address or org.address
        else:
            self.orgs[key] = org

    def seed_core_sources(self) -> None:
        self.progress("Seeding curated Estonian public-sector sources...")
        before = len(self.orgs)
        for name, url, org_type in CURATED_PUBLIC_SECTOR_SOURCES:
            self.add_org(
                OrganizationCandidate(
                    name=name,
                    type=org_type,
                    discovered_from={"curated_public_sector"},
                    raw_urls={url},
                )
            )
        self.progress(f"Seeded {len(self.orgs) - before} curated sources.")

    def urls_in_obj(self, obj: Any) -> Set[str]:
        found: Set[str] = set()
        if isinstance(obj, dict):
            for value in obj.values():
                found |= self.urls_in_obj(value)
        elif isinstance(obj, list):
            for value in obj:
                found |= self.urls_in_obj(value)
        elif isinstance(obj, str):
            for match in re.findall(r"https?://[^\s\"'<>]+", obj):
                url = normalize_url(match)
                if url:
                    found.add(url)
        return found

    def import_riha_systems(self) -> None:
        if not self.cfg.include_riha:
            self.progress("Skipping RIHA import (--no-include-riha).")
            return
        self.progress("Importing RIHA systems...")
        before = len(self.orgs)
        url = "https://www.riha.ee/api/v1/systems"
        response = self.http.get(url)
        if not response or response.status_code >= 400:
            logging.warning("RIHA unavailable")
            return
        try:
            data = response.json()
        except Exception:
            logging.warning("RIHA JSON parse failed")
            return
        items = (
            data.get("content")
            or data.get("items")
            or data.get("systems")
            or (data if isinstance(data, list) else [])
        )
        if not isinstance(items, list):
            return
        self.progress(f"RIHA returned {len(items)} systems; processing up to 500...")
        for item in items[:500]:
            name = (
                item.get("name")
                or item.get("short_name")
                or item.get("shortName")
                or item.get("title")
                or "RIHA system"
            )
            owner = (
                item.get("owner")
                or item.get("administrator")
                or item.get("organization")
            )
            if isinstance(owner, dict):
                owner = owner.get("name")
            urls = self.urls_in_obj(item)
            self.add_org(
                OrganizationCandidate(
                    str(owner or name),
                    type="riha_system",
                    parent=str(name),
                    discovered_from={"riha"},
                    raw_urls=urls,
                )
            )
        self.progress(
            f"RIHA import complete: added/updated {len(self.orgs) - before} organizations; total organizations: {len(self.orgs)}."
        )

    def import_e_business_register(self) -> None:
        path = self.cfg.e_business_register_file or os.getenv(
            "EBUSINESS_REGISTER_LOCAL_FILE"
        )
        remote = self.cfg.e_business_register_url or os.getenv(
            "EBUSINESS_REGISTER_JSON_URL"
        )
        if not path and not remote:
            self.progress(
                "Skipping e-Business Register import (no URL/file configured)."
            )
            return
        self.progress("Importing e-Business Register data...")
        before = len(self.orgs)
        try:
            if path:
                raw = (
                    gzip.open(path, "rt", encoding="utf-8").read()
                    if path.endswith(".gz")
                    else open(path, encoding="utf-8").read()
                )
                data = json.loads(raw)
            elif remote:
                response = self.http.get(remote)
                data = response.json() if response and response.ok else None
            else:
                return
        except Exception as exc:
            logging.warning("e-Business import failed: %s", exc)
            return
        if isinstance(data, list):
            rows = data
        elif isinstance(data, dict):
            rows = data.get("data") or data.get("items") or data.get("records") or []
        else:
            rows = []
        hints = (
            "riigi",
            "linna",
            "valla",
            "amet",
            "ministeer",
            "sihtasutus",
            "avalik-õigus",
            "omavalits",
        )
        for record in rows if isinstance(rows, list) else []:
            blob = json.dumps(record, ensure_ascii=False).lower()
            if not any(hint in blob for hint in hints):
                continue
            name = (
                record.get("name")
                or record.get("nimi")
                or record.get("arinimi")
                or record.get("business_name")
            )
            if not name:
                continue
            self.add_org(
                OrganizationCandidate(
                    str(name),
                    registry_code=str(
                        record.get("registry_code") or record.get("registrikood") or ""
                    )
                    or None,
                    type=str(
                        record.get("legal_type") or record.get("oiguslik_vorm") or ""
                    )
                    or None,
                    discovered_from={"e_business_register"},
                    raw_urls=self.urls_in_obj(record),
                    email=record.get("email")
                    or record.get("epost")
                    or record.get("e_mail"),
                    address=record.get("address") or record.get("aadress"),
                )
            )
        self.progress(
            f"e-Business Register import complete: added/updated {len(self.orgs) - before} organizations; total organizations: {len(self.orgs)}."
        )

    def import_data_portal(self) -> None:
        if not self.cfg.include_data_portal:
            self.progress(
                "Skipping Estonian Data Portal import (use --include-data-portal to enable)."
            )
            return
        self.progress("Importing Estonian Data Portal metadata...")
        before = len(self.orgs)
        for url in [
            "https://andmed.eesti.ee/api/3/action/package_search?rows=100",
            "https://andmed.eesti.ee/api/3/action/organization_list",
        ]:
            response = self.http.get(url)
            if not response or response.status_code >= 400:
                logging.warning("Data portal endpoint failed: %s", url)
                continue
            try:
                data = response.json()
            except Exception:
                continue
            result = data.get("result", {})
            items = result.get("results") if isinstance(result, dict) else result
            for item in items or []:
                if isinstance(item, str):
                    name = item
                    urls = {"https://andmed.eesti.ee"}
                else:
                    org = item.get("organization") if isinstance(item, dict) else {}
                    name = org.get("title") if isinstance(org, dict) else None
                    name = name or item.get("title") or item.get("name")
                    urls = self.urls_in_obj(item)
                if name:
                    self.add_org(
                        OrganizationCandidate(
                            str(name),
                            type="data_portal",
                            discovered_from={"data_portal"},
                            raw_urls=urls,
                        )
                    )
        self.progress(
            f"Data Portal import complete: added/updated {len(self.orgs) - before} organizations; total organizations: {len(self.orgs)}."
        )

    def fallback_signature(self, url: str) -> Optional[str]:
        base = base_url(url)
        key = domain(base)
        if key in self.fallback_signatures:
            return self.fallback_signatures[key]
        random_path = f"/__source_discovery_missing_{secrets.token_hex(8)}__"
        response = self.http.get(
            urljoin(base, random_path), timeout=min(5, self.cfg.timeout)
        )
        if not response or response.status_code != 200 or not response.text:
            self.fallback_signatures[key] = ""
            return None
        text = response.text[:5000].lower()
        if any(pattern in text for pattern in SOFT_404_PATTERNS):
            self.fallback_signatures[key] = content_signature(text)
            return self.fallback_signatures[key]
        content_type = response.headers.get("content-type", "").lower()
        self.fallback_signatures[key] = (
            content_signature(text) if "text/html" in content_type else ""
        )
        return self.fallback_signatures[key] or None

    def route_validity(
        self,
        route: RouteCandidate,
        response: Optional[requests.Response],
        text: str,
    ) -> Tuple[bool, str]:
        if not route.robots_allowed:
            return False, "robots disallowed"
        if route.http_status not in VALID_ROUTE_STATUSES:
            return False, f"http status {route.http_status or 'missing'}"
        if route.http_status in (401, 403):
            return route.access_method == "api_restricted", "restricted non-api route"
        content_type = (
            response.headers.get("content-type", "").lower() if response else ""
        )
        if any(content_type.startswith(kind) for kind in INVALID_CONTENT_TYPES):
            return False, f"unsupported content type {content_type}"
        if any(pattern in text for pattern in SOFT_404_PATTERNS):
            return False, "soft 404"
        if route.access_method in {"rss", "atom"} and not route.latest_items:
            return False, "feed had no items"
        if route.access_method == "sitemap" and not (
            "<urlset" in text[:1000] or "<sitemapindex" in text[:1000]
        ):
            return False, "sitemap endpoint returned non-sitemap content"
        if route.access_method == "api_public" and "json" not in content_type:
            return False, "api endpoint returned non-json content"
        fallback = self.fallback_signature(route.url)
        if fallback and content_signature(text) == fallback:
            return False, "matches missing-page fallback"
        if route.login_required:
            return False, "login required"
        if route.paywall_detected:
            return False, "paywall detected"
        if route.route_type in ARTICLE_ROUTE_TYPES and not self.is_archive_route(
            route.url
        ):
            return False, "not an archive/feed route"
        if route.route_type in ARTICLE_ROUTE_TYPES and not route.latest_items:
            return False, "no latest article/update links found"
        return True, ""

    def is_archive_route(self, url: str) -> bool:
        parsed = urlparse(url)
        path = parsed.path.lower().rstrip("/") or "/"
        query = parsed.query.lower()
        combined = f"{path}?{query}"
        if any(term in combined for term in BAD_ROUTE_TERMS):
            return False
        if re.search(r"/(uudised|news|pressiteated|press)/[^/?#]{12,}$", path):
            return False
        archive_patterns = (
            r"/uudised$",
            r"/et/uudised$",
            r"/ministeerium-uudised-ja-kontakt/uudised$",
            r"/ministeerium-uudised-ja-kontakt/uudised/(pressiteated|koned|statistika|lobistidega-kohtumised)$",
            r"/ministeerium-uudised-ja-kontakt/pressiteated$",
            r"/uudised-ja-pressiinfo/uudised$",
            r"/uudised-ja-pressiinfo/pressiteated$",
            r"/pressiteated$",
            r"/et/pressiteated$",
            r"/news$",
            r"/press$",
            r"/teated$",
            r"/teadaanded$",
            r"/aktuaalne$",
            r"/feed$",
            r"/rss$",
            r"/rss\.xml$",
            r"/atom\.xml$",
        )
        if any(re.search(pattern, path) for pattern in archive_patterns):
            return True
        return "type" in query and any(
            term in query for term in ("uudis", "news", "press")
        )

    def make_route(
        self,
        url: str,
        org: OrganizationCandidate,
        title: str = "",
        anchor_text: str = "",
        source_tags: Optional[Set[str]] = None,
    ) -> Optional[RouteCandidate]:
        normalized = normalize_url(url)
        if not normalized:
            return None
        allowed = self.http.robots_allowed(normalized)
        response = self.http.get(normalized) if allowed else None
        text = (
            response.text[:12000].lower()
            if response is not None and response.text
            else ""
        )
        status = response.status_code if response else None
        method = access_method(normalized, status)
        latest_items: List[LatestItem] = []
        if response and response.text and method in {"rss", "atom"}:
            latest_items = extract_feed_items(response.text)
        elif response and response.text and status == 200:
            latest_items = extract_html_items(response.text, normalized)
        route = RouteCandidate(
            url=normalized,
            route_type=classify_route(normalized, title, anchor_text),
            access_method=method,
            http_status=status,
            robots_allowed=allowed,
            title=title[:200],
            detected_keywords=keyword_hits(normalized, title, anchor_text, text[:3000]),
            latest_items=latest_items,
            last_checked_at=self.generated_at,
            source_tags=source_tags or set(),
            response_time=getattr(response, "elapsed_seconds", 0.0)
            if response
            else 0.0,
            login_required=("login" in text or "logi sisse" in text),
            paywall_detected=("paywall" in text),
        )
        route.valid, route.invalid_reason = self.route_validity(route, response, text)
        route.quality_score, route.quality_reasons = self.score_route(route, org)
        return route

    def score_route(
        self, route: RouteCandidate, org: OrganizationCandidate
    ) -> Tuple[int, List[str]]:
        score = 0
        reasons: List[str] = []
        tags = org.discovered_from | route.source_tags
        trust_points = [
            ("curated_public_sector", 40, "curated public sector"),
            ("riha", 25, "RIHA"),
            ("e_business_register", 30, "e-Business"),
            ("data_portal", 20, "data portal"),
        ]
        for tag, points, label in trust_points:
            if tag in tags:
                score += points
                reasons.append(label)
        if urlparse(route.url).scheme == "https":
            score += 10
            reasons.append("HTTPS")
        if route.access_method in ("rss", "atom"):
            score += 30
            reasons.append("feed")
        if route.route_type in {"news", "press_releases", "public_notices"}:
            score += 25
            reasons.append(route.route_type)
        if route.latest_items:
            score += min(20, 5 * len(route.latest_items))
            reasons.append(f"{len(route.latest_items)} latest items")
        if route.robots_allowed:
            score += 10
            reasons.append("robots allowed")
        if not route.valid:
            score -= 60
            reasons.append(route.invalid_reason)
        if route.response_time > self.cfg.timeout * 0.8:
            score -= 10
        return max(0, min(100, score)), reasons[:8]

    def estimate_domain_confidence(
        self, name: str, source_domain: str, evidence: Set[str]
    ) -> float:
        score = 0.25 + min(0.35, 0.1 * len(evidence))
        tokens = [
            token
            for token in re.sub(r"[^a-z0-9õäöüšž]+", " ", name.lower()).split()
            if len(token) > 3
        ]
        if any(token in source_domain.lower() for token in tokens):
            score += 0.2
        if source_domain.endswith(".ee"):
            score += 0.15
        return round(min(1.0, score), 2)

    def homepage_candidates(self, source_base: str) -> List[Tuple[str, str, Set[str]]]:
        response = self.http.get(source_base, timeout=min(8, self.cfg.timeout))
        if not response or response.status_code >= 400:
            return []
        try:
            parser = parse_page(response.text)
        except Exception:
            return []
        found: List[Tuple[str, str, Set[str]]] = []
        for feed_url in parser.feed_links:
            normalized = normalize_url(feed_url, source_base)
            if normalized:
                found.append((normalized, "feed declaration", {"homepage_feed"}))
        source_domain = domain(source_base)
        for href, text in parser.links:
            combined = f"{href} {text}".lower()
            if not any(keyword in combined for keyword in KEYWORDS):
                continue
            normalized = normalize_url(href, source_base)
            if normalized and domain(normalized) == source_domain:
                found.append((normalized, text, {"homepage_link"}))
        return found

    def sitemap_candidates(self, source_base: str) -> List[Tuple[str, str, Set[str]]]:
        found: List[Tuple[str, str, Set[str]]] = []
        for path in SITEMAP_PATHS:
            sitemap_url = urljoin(source_base, path)
            response = self.http.get(sitemap_url, timeout=min(8, self.cfg.timeout))
            if not response or response.status_code != 200:
                continue
            text = response.text
            for loc in re.findall(r"<loc>(.*?)</loc>", text, re.I)[:300]:
                if any(keyword in loc.lower() for keyword in KEYWORDS):
                    normalized = normalize_url(loc)
                    if normalized:
                        found.append((normalized, "sitemap match", {"sitemap"}))
        return found

    def fixed_path_candidates(
        self, source_base: str
    ) -> List[Tuple[str, str, Set[str]]]:
        return [
            (urljoin(source_base, path), "known path", {"known_path"})
            for path in KNOWN_PATHS + CMS_PATHS
        ]

    def candidate_routes(self, source_base: str) -> List[Tuple[str, str, Set[str]]]:
        candidates = []
        candidates.extend(self.homepage_candidates(source_base))
        candidates.extend(self.sitemap_candidates(source_base))
        candidates.extend(self.fixed_path_candidates(source_base))
        seen = set()
        unique = []
        for url, title, tags in candidates:
            normalized = normalize_url(url)
            if not normalized or normalized in seen:
                continue
            seen.add(normalized)
            unique.append((normalized, title, tags))
        unique.sort(
            key=lambda candidate: self.candidate_priority(candidate[0]), reverse=True
        )
        return unique[: self.cfg.max_routes_per_domain]

    def candidate_priority(self, url: str) -> int:
        parsed = urlparse(url)
        path = parsed.path.lower().rstrip("/") or "/"
        query = parsed.query.lower()
        value = f"{path}?{query}"
        score = 0
        if self.is_archive_route(url):
            score += 100
        if any(feed in path for feed in ("/feed", "/rss", "/rss.xml", "/atom.xml")):
            score += 30
        if "type" in query and any(
            term in query for term in ("uudis", "news", "press")
        ):
            score += 25
        if any(term in value for term in BAD_ROUTE_TERMS):
            score -= 100
        if re.search(r"/(uudised|news|pressiteated|press)/[^/?#]{12,}$", path):
            score -= 80
        return score

    def analyze_domain(self, org: OrganizationCandidate, source_base: str) -> None:
        source_domain = domain(source_base)
        self.progress(f"Analyzing domain: {source_domain} ({org.name})")
        health = self.http.get(source_base, timeout=min(5, self.cfg.timeout))
        if not health:
            self.progress(
                f"Skipping {source_domain}: domain did not respond or DNS failed."
            )
            return
        record = self.records.get(source_domain) or SourceRecord(
            organization=org,
            domain=source_domain,
            base_url=source_base,
            https=urlparse(source_base).scheme == "https",
            confidence=self.estimate_domain_confidence(
                org.name, source_domain, org.discovered_from
            ),
            verified_by=set(org.discovered_from),
        )
        candidates = self.candidate_routes(source_base)
        self.progress(
            f"  Checking {len(candidates)} route candidates for {source_domain}..."
        )
        seen = {route.url for route in record.routes}
        for index, (url, title, tags) in enumerate(candidates, 1):
            if url in seen:
                continue
            if index % 10 == 0:
                self.progress(
                    f"  {source_domain}: checked {index}/{len(candidates)}; kept {len(record.routes)} routes..."
                )
            route = self.make_route(
                url, org, title=title, anchor_text=title, source_tags=tags
            )
            if route and route.valid:
                record.routes.append(route)
                seen.add(url)
        if any(route.route_type in ARTICLE_ROUTE_TYPES for route in record.routes):
            self.records[source_domain] = record
        self.progress(f"Completed {source_domain}: kept {len(record.routes)} routes.")

    def resolve_domains(self) -> None:
        self.progress(
            f"Resolving and analyzing domains (max {self.cfg.max_domains})..."
        )
        seen_domains: Set[str] = set()
        count = 0
        for org in list(self.orgs.values()):
            for raw_url in sorted(org.raw_urls):
                normalized = normalize_url(raw_url)
                if not normalized:
                    continue
                source_base = base_url(normalized)
                source_domain = domain(source_base)
                if source_domain in seen_domains:
                    continue
                seen_domains.add(source_domain)
                self.analyze_domain(org, source_base)
                count += 1
                self.progress(
                    f"Domain progress: {count}/{self.cfg.max_domains} analyzed; {len(self.records)} usable domains found."
                )
                if count >= self.cfg.max_domains:
                    self.progress(
                        "Reached --max-domains limit; stopping domain analysis."
                    )
                    return

    def article_routes(self, record: SourceRecord) -> List[RouteCandidate]:
        routes = [
            route
            for route in record.routes
            if route.valid
            and route.route_type in ARTICLE_ROUTE_TYPES
            and route.latest_items
        ]
        routes.sort(key=lambda route: route.quality_score, reverse=True)
        return routes

    def export_json(self) -> None:
        self.progress(f"Exporting results to {self.cfg.output}...")
        sources = []
        route_count = high = 0
        for record in self.records.values():
            article_routes = self.article_routes(record)
            if not article_routes:
                continue
            route_count += len(article_routes)
            high += sum(1 for route in article_routes if route.quality_score >= 70)
            sources.append(
                {
                    "organization": {
                        "name": record.organization.name,
                        "registry_code": record.organization.registry_code,
                        "type": record.organization.type,
                        "parent": record.organization.parent,
                        "discovered_from": sorted(record.organization.discovered_from),
                    },
                    "confidence": record.confidence,
                    "website": record.base_url,
                    "domain": record.domain,
                    "articles_news_routes": [
                        {
                            "url": route.url,
                            "route_type": route.route_type,
                            "access_method": route.access_method,
                            "http_status": route.http_status,
                            "quality_score": route.quality_score,
                            "title": route.title,
                            "latest_items": [
                                {
                                    "title": item.title,
                                    "url": item.url,
                                    "published_at": item.published_at,
                                }
                                for item in route.latest_items
                            ],
                        }
                        for route in article_routes
                    ],
                }
            )
        root = {
            "generated_at": self.generated_at,
            "script_version": SCRIPT_VERSION,
            "country": "Estonia",
            "summary": {
                "organizations_discovered": len(self.orgs),
                "domains_discovered": len(self.records),
                "article_news_routes_discovered": route_count,
                "high_quality_article_news_routes": high,
            },
            "sources": sources,
        }
        with open(self.cfg.output, "w", encoding="utf-8") as file:
            json.dump(root, file, ensure_ascii=False, indent=2)
        self.progress(
            f"JSON export complete: {route_count} article/news routes across {len(sources)} exported domains."
        )

    def print_ranked_table(self) -> None:
        self.progress("Printing top ranked article/news routes...")
        rows = []
        for record in self.records.values():
            for route in self.article_routes(record):
                rows.append(
                    (
                        route.quality_score,
                        record.organization.name,
                        record.domain,
                        route,
                    )
                )
        rows.sort(reverse=True, key=lambda row: row[0])
        print(
            "| Rank | Organization | Domain | Route Type | Access | Score | URL | Reasons |"
        )
        print("|---:|---|---|---|---|---:|---|---|")
        for index, (score, name, source_domain, route) in enumerate(rows[:25], 1):
            reasons = "; ".join(route.quality_reasons)
            print(
                f"| {index} | {name[:60]} | {source_domain} | {route.route_type} | {route.access_method} | {score} | {route.url} | {reasons} |"
            )

    def run(self) -> None:
        self.start_time = time.time()
        self.progress("Starting Estonian public-sector source discovery.")
        self.seed_core_sources()
        self.import_e_business_register()
        self.import_riha_systems()
        self.import_data_portal()
        self.resolve_domains()
        self.export_json()
        self.print_ranked_table()
        elapsed = time.time() - self.start_time
        self.progress(
            f"Finished in {elapsed:.1f} seconds ({elapsed / 60:.1f} minutes)."
        )
