# Extracting News URLs

Input:

```text
finding-sources/public_sector_sources.json
```

Run:

```bash
python3 extracting-urls/extract_news_urls.py
```

Outputs:

```text
extracting-urls/news_urls.json
extracting-urls/errors.json
```

Each article object preserves the source name/domain, source route, discovered
title, route type, discovery timestamp, and URL discovery method.
