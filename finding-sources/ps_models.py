from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional, Set

SCRIPT_VERSION = "0.2"
DEFAULT_UA = "PublicSectorSourceDiscoveryBot/0.2 (+contact@example.com)"

BAD_DOMAINS = (
    "facebook.com",
    "twitter.com",
    "x.com",
    "instagram.com",
    "linkedin.com",
    "youtube.com",
    "youtu.be",
)

ARTICLE_ROUTE_TYPES = {"news", "press_releases", "public_notices", "rss", "atom"}

KEYWORDS = [
    "uudised",
    "uudis",
    "pressiteated",
    "pressiteade",
    "teated",
    "teadaanded",
    "ametlikud teadaanded",
    "aktuaalne",
    "meediale",
    "kommunikatsioon",
    "dokumendid",
    "dokumendiregister",
    "kaasamine",
    "avalikud arutelud",
    "hanked",
    "riigihanked",
    "planeeringud",
    "toetused",
    "konkursid",
    "istungid",
    "otsused",
    "news",
    "press",
    "media",
    "notices",
    "announcements",
    "documents",
    "procurement",
    "tenders",
    "consultation",
    "public consultation",
    "planning",
    "grants",
    "decisions",
]

SOFT_404_PATTERNS = (
    "lehekülge ei leitud",
    "lehte ei leitud",
    "page not found",
    "404 not found",
    "not-found",
)

INVALID_CONTENT_TYPES = (
    "image/",
    "video/",
    "audio/",
    "font/",
    "application/octet-stream",
)

KNOWN_PATHS = [
    "/uudised",
    "/et/uudised",
    "/ministeerium-uudised-ja-kontakt/uudised",
    "/ministeerium-uudised-ja-kontakt/uudised/pressiteated",
    "/ministeerium-uudised-ja-kontakt/uudised/koned",
    "/ministeerium-uudised-ja-kontakt/uudised/statistika",
    "/ministeerium-uudised-ja-kontakt/uudised/lobistidega-kohtumised",
    "/ministeerium-uudised-ja-kontakt/pressiteated",
    "/uudised-ja-pressiteated",
    "/et/uudised-ja-pressiteated",
    "/uudised-ja-pressiinfo/uudised",
    "/uudised-ja-pressiinfo/pressiteated",
    "/pressiteated",
    "/et/pressiteated",
    "/meediale",
    "/et/meediale",
    "/news",
    "/press",
    "/teated",
    "/teadaanded",
    "/aktuaalne",
    "/feed",
    "/rss",
    "/rss.xml",
    "/atom.xml",
]

SITEMAP_PATHS = ["/sitemap.xml", "/sitemap_index.xml"]

CMS_PATHS = ["/wp-json/wp/v2/posts", "/jsonapi"]

CURATED_PUBLIC_SECTOR_SOURCES = [
    ("Vabariigi Valitsus", "https://www.valitsus.ee", "government"),
    ("Rahandusministeerium", "https://www.fin.ee", "ministry"),
    ("Justiits- ja Digiministeerium", "https://www.justdigi.ee", "ministry"),
    ("Regionaal- ja Põllumajandusministeerium", "https://www.agri.ee", "ministry"),
    ("Kaitseministeerium", "https://www.kaitseministeerium.ee", "ministry"),
    ("Kliimaministeerium", "https://www.kliimaministeerium.ee", "ministry"),
    ("Kultuuriministeerium", "https://www.kul.ee", "ministry"),
    ("Siseministeerium", "https://www.siseministeerium.ee", "ministry"),
    ("Sotsiaalministeerium", "https://www.sm.ee", "ministry"),
    ("Haridus- ja Teadusministeerium", "https://www.hm.ee", "ministry"),
    ("Välisministeerium", "https://www.vm.ee", "ministry"),
    ("Majandus- ja Kommunikatsiooniministeerium", "https://www.mkm.ee", "ministry"),
    ("Riigi Infosüsteemi Amet", "https://www.ria.ee", "agency"),
    ("Politsei- ja Piirivalveamet", "https://www.politsei.ee", "agency"),
    ("Päästeamet", "https://www.rescue.ee", "agency"),
    ("Terviseamet", "https://www.terviseamet.ee", "agency"),
    ("Maksu- ja Tolliamet", "https://www.emta.ee", "agency"),
    ("Transpordiamet", "https://www.transpordiamet.ee", "agency"),
    ("Statistikaamet", "https://www.stat.ee", "agency"),
    ("Keskkonnaamet", "https://www.keskkonnaamet.ee", "agency"),
    ("Maa-amet", "https://www.maaamet.ee", "agency"),
    ("Tarbijakaitse ja Tehnilise Järelevalve Amet", "https://www.ttja.ee", "agency"),
    ("Konkurentsiamet", "https://www.konkurentsiamet.ee", "agency"),
    ("Ametlikud Teadaanded", "https://www.ametlikudteadaanded.ee", "public_notices"),
    ("Riigihangete register", "https://riigihanked.riik.ee", "procurement"),
]


@dataclass
class Config:
    output: str = "public_sector_sources.json"
    max_domains: int = 100
    max_routes_per_domain: int = 50
    timeout: int = 15
    contact_email: str = "contact@example.com"
    e_business_register_file: Optional[str] = None
    e_business_register_url: Optional[str] = None
    include_data_portal: bool = False
    include_riha: bool = True
    verbose: bool = False
    delay: float = 1.0


@dataclass
class OrganizationCandidate:
    name: str
    registry_code: Optional[str] = None
    type: Optional[str] = None
    parent: Optional[str] = None
    discovered_from: Set[str] = field(default_factory=set)
    raw_urls: Set[str] = field(default_factory=set)
    email: Optional[str] = None
    address: Optional[str] = None


@dataclass
class LatestItem:
    title: str
    url: str
    published_at: str = ""


@dataclass
class RouteCandidate:
    url: str
    route_type: str = "unknown"
    access_method: str = "unknown"
    http_status: Optional[int] = None
    robots_allowed: Optional[bool] = None
    title: str = ""
    detected_keywords: List[str] = field(default_factory=list)
    latest_items: List[LatestItem] = field(default_factory=list)
    last_checked_at: str = ""
    quality_score: int = 0
    quality_reasons: List[str] = field(default_factory=list)
    source_tags: Set[str] = field(default_factory=set)
    response_time: float = 0.0
    login_required: bool = False
    paywall_detected: bool = False
    valid: bool = False
    invalid_reason: str = ""


@dataclass
class SourceRecord:
    organization: OrganizationCandidate
    domain: str
    base_url: str
    https: bool
    confidence: float
    verified_by: Set[str] = field(default_factory=set)
    routes: List[RouteCandidate] = field(default_factory=list)
