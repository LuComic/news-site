# Full Pipeline

`run_pipeline.py` runs the whole public-sector news extraction flow from the
repository root.

It performs three stages:

1. Source discovery.
2. News URL extraction.
3. Combined article content extraction.

Run the full pipeline:

```bash
python3 run_pipeline.py
```

Run a small test:

```bash
python3 run_pipeline.py --limit 5
```

## Stage 1: Source Discovery

The first stage runs:

```bash
python3 finding-sources/discover_public_sector_sources.py
```

It discovers public-sector websites and their news, press release, RSS, Atom,
and article listing routes. The default output is:

```text
finding-sources/public_sector_sources.json
```

This file becomes the input for URL extraction.

## Stage 2: URL Extraction

The second stage runs:

```bash
python3 extracting-urls/extract_news_urls.py
```

It reads discovered `articles_news_routes` from:

```text
finding-sources/public_sector_sources.json
```

Then it extracts actual article/news URLs from RSS/Atom feeds, VPortal/Drupal
search/listing pages, and normal HTML listing pages.

Default outputs:

```text
extracting-urls/news_urls.json
extracting-urls/errors.json
```

`news_urls.json` is a JSON array. Each object represents one discovered article
URL and keeps source metadata such as `source_domain`, `source_name`,
`route_url`, `route_type`, `discovered_title`, and `discovery_method`.

## Stage 3: Combined Extraction

The final stage reads:

```text
extracting-urls/news_urls.json
```

It extracts one best article result per URL using a fallback chain:

1. Deterministic site-family selectors. (method 1)
2. Trafilatura generic article extraction. (method 3)
3. Readability-style boilerplate removal. (method 4)
4. Feed-based extraction, only for feed-backed URLs. (method 2)

Each successful article keeps:

```text
extraction_method
combined_extraction_method
fallback_chain
```

For example, if Method 1 succeeds:

```json
{
  "extraction_method": "deterministic_site_family_selectors",
  "combined_extraction_method": "combined_fallback_extractor",
  "fallback_chain": ["deterministic_site_family_selectors:success"]
}
```

If Method 1 fails but Trafilatura succeeds, `fallback_chain` records that path.

Default final outputs:

```text
output/articles.json
output/errors.json
output/markdowns/
```

## Arguments

### `--output-dir`

Final combined extraction output directory.

Default:

```text
output
```

Example:

```bash
python3 run_pipeline.py --output-dir output/test-run
```

Writes:

```text
output/test-run/articles.json
output/test-run/errors.json
output/test-run/markdowns/
```

### `--sources-output`

Path where source discovery writes `public_sector_sources.json`.

Default:

```text
finding-sources/public_sector_sources.json
```

Example:

```bash
python3 run_pipeline.py --sources-output output/public_sector_sources.json
```

This same path is passed into the URL extraction stage.

### `--urls-output`

Path where URL extraction writes discovered article URLs, and where combined
extraction reads them from.

Default:

```text
extracting-urls/news_urls.json
```

Example:

```bash
python3 run_pipeline.py --urls-output output/news_urls.json
```

### `--url-errors-output`

Path where URL extraction writes route/URL discovery errors.

Default:

```text
extracting-urls/errors.json
```

Example:

```bash
python3 run_pipeline.py --url-errors-output output/url_errors.json
```

These are URL discovery errors, not article content extraction errors. Final
content extraction errors are written to:

```text
output/errors.json
```

or whichever directory was set with `--output-dir`.

### `--limit`

Limits how many discovered article URLs are processed by the final combined
content extraction stage.

Default:

```text
no limit
```

Example:

```bash
python3 run_pipeline.py --limit 5
```

Important: this does not limit source discovery or URL extraction. It limits the
final article content extraction stage.

### `--timeout`

HTTP timeout in seconds for source discovery, URL extraction, and article
fetching.

Default:

```text
25
```

Example:

```bash
python3 run_pipeline.py --timeout 45
```

Use a larger value if public-sector sites are slow or temporarily overloaded.

### `--delay`

Delay in seconds between URL extraction route requests.

Default:

```text
0.35
```

Example:

```bash
python3 run_pipeline.py --delay 1.0
```

Use a larger value for a more polite crawl.

### `--max-domains`

Maximum number of domains analyzed during source discovery.

Default:

```text
100
```

Example:

```bash
python3 run_pipeline.py --max-domains 25
```

This is mainly useful for smaller discovery runs while testing.

### `--max-routes-per-domain`

Maximum number of candidate routes retained per discovered domain during source
discovery.

Default:

```text
50
```

Example:

```bash
python3 run_pipeline.py --max-routes-per-domain 20
```

### `--include-data-portal`

Also use the Estonian Data Portal during source discovery.

Default:

```text
disabled
```

Example:

```bash
python3 run_pipeline.py --include-data-portal
```

This may discover more sources, but can make source discovery slower.

### `--no-riha`

Disable RIHA-based source discovery.

Default:

```text
RIHA discovery enabled
```

Example:

```bash
python3 run_pipeline.py --no-riha
```

Use this when you only want curated/core sources and do not want RIHA system URLs
included.

### `--skip-source-finding`

Skip Stage 1 and reuse the existing source file.

Example:

```bash
python3 run_pipeline.py --skip-source-finding
```

The script will expect the file from `--sources-output` to already exist.

### `--skip-url-extraction`

Skip Stage 2 and reuse the existing URL file.

Example:

```bash
python3 run_pipeline.py --skip-url-extraction
```

The script will expect the file from `--urls-output` to already exist.

## Common Commands

Full run:

```bash
python3 run_pipeline.py
```

Small end-to-end test:

```bash
python3 run_pipeline.py --limit 5
```

Only rerun final article extraction from existing URLs:

```bash
python3 run_pipeline.py --skip-source-finding --skip-url-extraction --limit 5
```

Write final results somewhere else:

```bash
python3 run_pipeline.py --output-dir output/run-001
```

Use existing source and URL files in custom locations:

```bash
python3 run_pipeline.py \
  --skip-source-finding \
  --skip-url-extraction \
  --sources-output output/public_sector_sources.json \
  --urls-output output/news_urls.json \
  --output-dir output/final
```

## Final Output Shape

`articles.json` is a JSON array of article records.

Each record contains fields such as:

```text
url
source_domain
source_name
title
lead
body_text
body_markdown
author
published_at
modified_at
tags
language
images
links
extraction_method
combined_extraction_method
fallback_chain
extraction_confidence
content_length_chars
paragraph_count
retrieved_at
```

`errors.json` is a JSON array of failed extraction attempts. If one fallback
method fails but a later fallback succeeds, the article still appears in
`articles.json`; failed attempts are only written to final `errors.json` when no
method succeeds for that URL.

`markdowns/` contains one Markdown file per successfully extracted article.
