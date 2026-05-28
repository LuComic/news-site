High-level outline of how `discover_public_sector_sources.py` works.

## 1. CLI wrapper

`discover_public_sector_sources.py` is intentionally small. It parses CLI flags, configures logging, and runs `SourceDiscovery`.

Most implementation is split into helper modules:

- `ps_models.py`: dataclasses, constants, curated source seeds, route paths
- `ps_http.py`: polite HTTP client, retries, per-domain delay, robots.txt
- `ps_parsing.py`: URL normalization, HTML/feed parsing, route classification
- `ps_discovery.py`: importers, domain analysis, validation, scoring, JSON export

---

## 2. Seeds real public-sector websites first

The script no longer relies mainly on RIHA system URLs. It starts from curated Estonian public-sector organizations that are likely to publish news, press releases, or updates:

- ministries
- major state agencies
- Vabariigi Valitsus
- Ametlikud Teadaanded
- Riigihangete register

These seeds are tagged as `curated_public_sector` and get high trust in scoring.

---

## 3. Imports optional extra candidates

The script still supports broader discovery from:

- RIHA (`--include-riha`, enabled by default)
- e-Business Register file or URL
- Estonian Data Portal (`--include-data-portal`)

These imports add candidate organizations and raw URLs, but a source is only exported if a usable article/news/press route is found.

---

## 4. Discovers routes from site structure first

For each domain, the analyzer checks the homepage and extracts:

- declared RSS/Atom feed links
- internal links whose text or URL contains public-sector news/update keywords

Then it checks sitemap URLs for matching news/update URLs.

Only after that does it try known archive paths such as:

```text
/uudised
/pressiteated
/ministeerium-uudised-ja-kontakt/uudised
/uudised-ja-pressiinfo/uudised
/feed
/rss.xml
```

The script does not crawl the whole website.

---

## 5. Validates routes strictly

A route is kept only if it is public and useful:

- robots.txt allows it
- HTTP status is valid
- it is not a soft 404 such as `lehekülge ei leitud`
- it does not match the site’s missing-page fallback
- it is not a contact/job/privacy/organization page
- it is an archive/search/feed route, not an individual article URL
- it exposes latest article/update items

This prevents RIHA-style fake `200 OK` paths from entering the output.

---

## 6. Extracts newest items

For RSS/Atom feeds, the script parses feed entries.

For HTML archive/search pages, it extracts same-domain links that look like article or press-release items, for example:

```text
/uudised/some-current-press-release
/pressiteated/some-current-notice
/2026/05/...
```

These are exported under each route as `latest_items`.

---

## 7. Scores source-route quality

Routes are scored from 0 to 100 using:

- curated public-sector trust
- RIHA/e-Business/Data Portal evidence
- HTTPS
- RSS/Atom support
- route type
- number of latest items found
- robots.txt allowance
- validation failures and slow responses

This is source quality scoring, not article ranking.

---

## 8. Exports only useful sources

The output file is:

```text
public_sector_sources.json
```

Sources with empty `articles_news_routes` are omitted. If a site has no valid news/article/press/update route, it is not useful for this pipeline and is not exported.
