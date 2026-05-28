You are a senior data engineer and web discovery engineer.

Write a production-oriented Python 3 script that automatically discovers official Estonian public-sector information sources and identifies their news, press release, public notice, procurement, consultation, planning, and document routes.

Important: do not build news ranking, user voting, recommendation logic, or ML summarization yet. This task is only about source discovery, route discovery, JSON export, and a final source-quality table.

The final output should be a working script.

The script must:

1. discover public-sector organizations, agencies, registries, and public information systems from official or semi-official machine-readable sources;
2. identify each organization’s or system’s likely official website/domain;
3. analyze each domain for:
   - robots.txt
   - sitemap.xml
   - RSS/Atom feeds
   - CMS endpoints
   - news routes
   - press release routes
   - public notice routes
   - document register routes
   - consultation routes
   - procurement routes
   - planning routes
   - grant/support routes
4. score each discovered route by technical quality and source reliability;
5. save all results into a JSON file;
6. print a final markdown table of the best discovered sources in ranked source-quality format.

Use the following discovery sources.

A. e-Business Register open data

The Estonian e-Business Register open data contains public data about companies, non-profit associations, foundations, and state and local government institutions in machine-readable JSON/XML formats.

The script must support either:
- a configurable e-Business Register open data URL; or
- a local file path to a previously downloaded dataset.

Use these configuration values:

- EBUSINESS_REGISTER_JSON_URL
- EBUSINESS_REGISTER_LOCAL_FILE

If neither is provided, skip this importer gracefully and continue with the other discovery sources.

The importer should attempt to extract:

- organization name
- registry code
- legal type
- status
- address, if available
- website URL, if available
- email, if available
- any other URL-like values

Filter or prioritize records that appear to be:

- state agencies
- municipal agencies
- public-law bodies
- public-sector foundations
- local government organizations
- state-owned or municipality-owned institutions, where this can be inferred

Do not hard-fail if the exact schema is different. Implement flexible field extraction.

B. RIHA API

Use RIHA as a discovery source for Estonian public-sector information systems.

RIHA API base URL:

https://www.riha.ee/api/v1

Main systems endpoint:

https://www.riha.ee/api/v1/systems

The script must:

- request the /systems endpoint;
- extract system name, short name, owner/administrator, description, status, and any URLs found in the machine-readable payload;
- add each system and each discovered URL as a source candidate;
- optionally fetch detailed system records if the list endpoint provides IDs or short names;
- handle pagination or alternative response shapes if present;
- continue gracefully if the endpoint is temporarily unavailable.

C. Estonian Data Portal

Use the Estonian Data Portal as an optional discovery source.

Base:

https://andmed.eesti.ee

Try CKAN-style endpoints first:

- /api/3/action/package_search
- /api/3/action/organization_list
- /api/3/action/package_show

Also try the documented dataset API if available.

From the data portal, extract:

- dataset publishers
- organizations
- dataset landing pages
- distribution URLs
- API URLs
- contact points
- public-sector owner names
- public-sector system names

If the API shape is different or the endpoint fails, log a warning and continue.

D. Ametlikud Teadaanded

Always include Ametlikud Teadaanded as a core source.

Base:

https://www.ametlikudteadaanded.ee

The script must try to discover and/or validate:

- /eng/uriotsing
- /avalik/uriotsing
- /robots.txt
- /sitemap.xml
- HTML reuse routes
- XML reuse routes
- XML-RDF reuse routes

Add it as a high-priority official public notice source even if normal discovery does not find it.

E. Riigihangete register

Always include the Estonian Public Procurement Register as a core source.

Base:

https://riigihanked.riik.ee

The script must try:

- /robots.txt
- /sitemap.xml
- public API routes found from HTML links or route probing
- route patterns containing /rhr/api/public/

Add it as a high-priority procurement source.

F. Domain-based discovery

For every discovered organization/system domain, run a site analyzer.

The site analyzer must check at least these paths:

- /robots.txt
- /sitemap.xml
- /sitemap_index.xml
- /feed
- /rss
- /atom.xml
- /et/uudised
- /uudised
- /news
- /press
- /pressiteated
- /teated
- /teadaanded
- /ametlikud-teadaanded
- /dokumendid
- /dokumendiregister
- /kaasamine
- /avalikud-arutelud
- /hanked
- /riigihanked
- /planeeringud
- /toetused
- /kontakt
- /meediale

Also parse the homepage HTML and sitemap URLs for links where the anchor text or href contains any of these keywords.

Estonian keywords:

- uudised
- uudis
- pressiteated
- pressiteade
- teated
- teadaanded
- ametlikud teadaanded
- aktuaalne
- meediale
- dokumendid
- dokumendiregister
- kaasamine
- avalikud arutelud
- hanked
- riigihanked
- planeeringud
- toetused
- konkursid
- istungid
- otsused

English keywords:

- news
- press
- media
- notices
- announcements
- documents
- procurement
- tenders
- consultation
- public consultation
- planning
- grants
- decisions

Russian keywords, if easy to add:

- новости
- объявления
- пресс
- документы

G. CMS and API discovery

For every discovered domain, test the following endpoint patterns.

WordPress:

- /wp-json/
- /wp-json/wp/v2/posts
- /feed

Drupal:

- /jsonapi
- /rss.xml

Generic:

- /api
- /graphql
- /sitemap.xml
- /robots.txt

If an endpoint returns HTTP 200, 401, or 403, save it as a candidate.

Set access_method as one of:

- api_public
- api_restricted
- rss
- atom
- sitemap
- html
- robots
- unknown

H. Robots.txt and polite crawling

The script must:

- fetch and parse robots.txt;
- use urllib.robotparser or an equivalent approach;
- avoid aggressive crawling;
- use per-domain rate limiting;
- send a clear User-Agent;
- support configurable timeout and retry settings;
- use exponential backoff for 429, 500, 502, 503, and 504 responses;
- never try to bypass access restrictions;
- never scrape paywalled or login-only content;
- only save public URLs.

Use this default User-Agent:

PublicSectorSourceDiscoveryBot/0.1 (+contact@example.com)

Make the contact email configurable.

I. Source candidate scoring

The script should compute a technical source-quality score for each discovered content route.

This is not news ranking. This is only source discovery quality scoring.

Suggested scoring:

Base trust:

+30 if source came from RIHA
+30 if source came from e-Business Register open data
+25 if source came from Estonian Data Portal
+35 if source is one of the hardcoded core official sources
+15 if domain appears to match the organization name
+10 if domain is clearly Estonian public-sector related
+10 if HTTPS is available

Machine-readable access:

+25 if RSS/Atom exists
+30 if public API exists
+20 if sitemap exists
+15 if CMS JSON endpoint exists
+10 if page has structured metadata such as JSON-LD, OpenGraph, or article timestamps

Content route quality:

+25 if route looks like a news or press release archive
+25 if route looks like a public notices archive
+20 if route looks like a document register
+20 if route looks like procurement/tenders
+15 if route looks like public consultations
+15 if route looks like planning notices
+10 if route has recent-looking URLs or dates

Safety and crawlability:

+15 if robots.txt allows crawling
-40 if robots.txt disallows the route
-30 if the page requires login
-25 if the page appears paywalled
-15 if HTTP status is 404
-10 if HTTP status is 500+
-10 if response is too slow
-15 if duplicate of another source

The score should be normalized to 0–100.

J. Output JSON schema

Save results to:

public_sector_sources.json

The JSON root must be an object:

{
  "generated_at": "...",
  "script_version": "0.1",
  "country": "Estonia",
  "summary": {
    "organizations_discovered": 0,
    "domains_discovered": 0,
    "routes_discovered": 0,
    "high_quality_routes": 0
  },
  "sources": []
}

Each source object should look like this:

{
  "organization": {
    "name": "...",
    "registry_code": "...",
    "type": "...",
    "parent": "...",
    "discovered_from": ["riha", "e_business_register", "data_portal"]
  },
  "website": {
    "domain": "...",
    "base_url": "...",
    "https": true,
    "confidence": 0.0,
    "verified_by": ["riha", "sitemap", "domain_match"]
  },
  "routes": [
    {
      "url": "...",
      "route_type": "news | press_releases | public_notices | procurement | documents | consultations | planning | grants | rss | api | sitemap | unknown",
      "access_method": "html | rss | atom | api_public | api_restricted | sitemap | unknown",
      "http_status": 200,
      "robots_allowed": true,
      "title": "...",
      "detected_keywords": [],
      "last_checked_at": "...",
      "quality_score": 0,
      "quality_reasons": []
    }
  ],
  "discovery": {
    "first_seen_at": "...",
    "last_checked_at": "...",
    "discovery_sources": [],
    "raw_candidate_urls": []
  },
  "legal": {
    "public_sector_source": true,
    "paywall_detected": false,
    "login_required": false,
    "robots_checked": true
  }
}

K. Final terminal table

After writing the JSON file, print a markdown table with the best discovered routes.

Columns:

- Rank
- Organization
- Domain
- Route Type
- Access
- Score
- URL
- Reasons

Sort by quality_score descending.

Only print the top 25 routes.

Example table:

| Rank | Organization | Domain | Route Type | Access | Score | URL | Reasons |
|---:|---|---|---|---|---:|---|---|
| 1 | Ametlikud Teadaanded | ametlikudteadaanded.ee | public_notices | xml | 96 | https://... | core official source; reusable URI; XML supported |
| 2 | RIHA | riha.ee | api | api_public | 94 | https://www.riha.ee/api/v1/systems | official registry; public API |

L. Implementation requirements

Use Python 3.11+.

Prefer these libraries:

- requests or httpx
- beautifulsoup4
- lxml if useful
- feedparser for RSS/Atom
- tldextract if useful
- urllib.robotparser
- urllib.parse
- dataclasses
- typing
- json
- time
- re
- hashlib
- datetime
- logging

The script must be runnable as:

python discover_public_sector_sources.py

Support optional CLI arguments:

--output public_sector_sources.json
--max-domains 200
--max-routes-per-domain 50
--timeout 15
--contact-email your@email.com
--e-business-register-file path/to/file.json
--e-business-register-url https://...
--include-data-portal
--include-riha
--verbose

Make defaults safe:

- include RIHA by default
- include hardcoded core sources by default
- include data portal only if --include-data-portal is provided, unless implementation is simple and safe
- max domains default 100
- timeout default 15 seconds
- delay between requests to same domain at least 1 second

M. Robustness requirements

The script must:

- not crash when a source is unavailable;
- log warnings instead of failing the whole run;
- deduplicate domains and URLs;
- normalize URLs;
- convert relative links to absolute links;
- remove URL fragments;
- avoid infinite crawling;
- never crawl the whole website;
- only inspect homepage, known paths, sitemap URLs, feed URLs, and discovered candidate links;
- cap the number of inspected URLs per domain;
- handle gzip and redirects;
- handle invalid SSL gracefully with warnings, but do not disable SSL verification by default.

N. Route classification

Implement a function classify_route(url, title, anchor_text) that returns one of:

- news
- press_releases
- public_notices
- procurement
- documents
- consultations
- planning
- grants
- rss
- atom
- api
- sitemap
- contact
- unknown

Use keyword rules. Keep it simple and explainable.

Examples:

- “uudised”, “news” => news
- “pressiteated”, “press release”, “press” => press_releases
- “teadaanded”, “notices”, “ametlikud teadaanded” => public_notices
- “hanked”, “riigihanked”, “procurement”, “tenders” => procurement
- “dokumendiregister”, “documents” => documents
- “kaasamine”, “consultation”, “avalikud arutelud” => consultations
- “planeeringud”, “planning” => planning
- “toetused”, “grants” => grants
- “rss”, “feed” => rss
- “api”, “jsonapi”, “wp-json”, “graphql” => api
- “sitemap” => sitemap

O. Domain confidence

Implement a function estimate_domain_confidence(organization_name, domain, evidence_sources).

The confidence should be 0.0–1.0.

Consider:

- URL was directly provided by RIHA/e-Business Register/Data Portal;
- domain contains normalized organization name tokens;
- domain is not a social media or private news domain;
- HTTPS works;
- site title mentions organization name;
- multiple discovery sources agree on same domain.

P. Core source seeds

Always seed these sources:

1. Ametlikud Teadaanded
   base_url: https://www.ametlikudteadaanded.ee
   type: public_notices
   trust: official_core

2. RIHA
   base_url: https://www.riha.ee
   api_url: https://www.riha.ee/api/v1/systems
   type: public_registry
   trust: official_core

3. Riigihangete register
   base_url: https://riigihanked.riik.ee
   type: procurement
   trust: official_core

4. Eesti.ee
   base_url: https://www.eesti.ee
   type: public_services
   trust: official_core

5. Estonian Data Portal
   base_url: https://andmed.eesti.ee
   type: open_data
   trust: official_core

Q. Code structure

Use this structure:

- Config dataclass
- OrganizationCandidate dataclass
- RouteCandidate dataclass
- SourceRecord dataclass
- HttpClient class with rate limiting and retry
- SourceDiscovery class
  - import_e_business_register()
  - import_riha_systems()
  - import_data_portal()
  - seed_core_sources()
  - resolve_domains()
  - analyze_domain()
  - discover_sitemap_routes()
  - discover_feed_routes()
  - discover_homepage_links()
  - discover_known_paths()
  - discover_cms_endpoints()
  - classify_route()
  - score_route()
  - export_json()
  - print_ranked_table()

R. Deliverable

Return only the complete Python script in one code block.

Do not return explanations outside the code block.

The script should be useful even if some official APIs or datasets are unavailable during runtime.
