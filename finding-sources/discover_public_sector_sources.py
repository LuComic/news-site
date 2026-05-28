#!/usr/bin/env python3
"""Discover Estonian public-sector news, press release, and update sources."""

from __future__ import annotations

import argparse
import logging

from ps_discovery import SourceDiscovery
from ps_models import Config


def parse_args() -> Config:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="public_sector_sources.json")
    parser.add_argument("--max-domains", type=int, default=100)
    parser.add_argument("--max-routes-per-domain", type=int, default=50)
    parser.add_argument("--timeout", type=int, default=15)
    parser.add_argument("--contact-email", default="contact@example.com")
    parser.add_argument("--e-business-register-file")
    parser.add_argument("--e-business-register-url")
    parser.add_argument("--include-data-portal", action="store_true")
    parser.add_argument(
        "--include-riha", action=argparse.BooleanOptionalAction, default=True
    )
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()
    return Config(**vars(args))


if __name__ == "__main__":
    cfg = parse_args()
    logging.basicConfig(
        level=logging.DEBUG if cfg.verbose else logging.INFO,
        format="%(levelname)s: %(message)s",
    )
    SourceDiscovery(cfg).run()
