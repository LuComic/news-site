from __future__ import annotations

import logging
import time
from typing import Dict, Optional, Set
from urllib.parse import urljoin, urlparse
from urllib.robotparser import RobotFileParser

import requests
from ps_models import DEFAULT_UA, Config

RETRY_STATUSES = {429, 500, 502, 503, 504}


class HttpClient:
    def __init__(self, cfg: Config):
        self.cfg = cfg
        self.session = requests.Session()
        ua = DEFAULT_UA.replace("contact@example.com", cfg.contact_email)
        self.session.headers.update(
            {
                "User-Agent": ua,
                "Accept": "text/html,application/xhtml+xml,application/xml,application/json,*/*",
            }
        )
        self.last_hit: Dict[str, float] = {}
        self.robots: Dict[str, RobotFileParser] = {}
        self.dead_domains: Set[str] = set()

    def _domain(self, url: str) -> str:
        return urlparse(url).netloc.lower()

    def get(self, url: str, **kwargs) -> Optional[requests.Response]:
        domain = self._domain(url)
        if domain in self.dead_domains:
            return None
        now = time.time()
        wait = self.cfg.delay - (now - self.last_hit.get(domain, 0))
        if wait > 0:
            time.sleep(wait)
        timeout = kwargs.pop("timeout", self.cfg.timeout)
        for attempt in range(3):
            try:
                start = time.time()
                response = self.session.get(
                    url, timeout=timeout, allow_redirects=True, **kwargs
                )
                response.elapsed_seconds = time.time() - start  # type: ignore[attr-defined]
                self.last_hit[domain] = time.time()
                if response.status_code in RETRY_STATUSES and attempt < 2:
                    time.sleep(2**attempt)
                    continue
                return response
            except requests.RequestException as exc:
                logging.warning("GET failed %s: %s", url, exc)
                msg = str(exc).lower()
                if any(
                    text in msg
                    for text in [
                        "failed to resolve",
                        "name or service not known",
                        "nodename nor servname",
                        "temporary failure in name resolution",
                    ]
                ):
                    self.dead_domains.add(domain)
                    return None
                if attempt < 2:
                    time.sleep(2**attempt)
        return None

    def robots_allowed(self, url: str) -> bool:
        parsed = urlparse(url)
        base = f"{parsed.scheme}://{parsed.netloc}"
        key = parsed.netloc.lower()
        if key not in self.robots:
            rp = RobotFileParser()
            robots_url = urljoin(base, "/robots.txt")
            rp.set_url(robots_url)
            try:
                response = self.get(robots_url, timeout=min(5, self.cfg.timeout))
                lines = (
                    response.text.splitlines()
                    if response and response.status_code < 500
                    else []
                )
                rp.parse(lines)
            except Exception:
                rp.parse([])
            self.robots[key] = rp
        user_agent = str(self.session.headers["User-Agent"])
        return self.robots[key].can_fetch(user_agent, url)
