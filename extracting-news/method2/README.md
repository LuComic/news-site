# Method 2

Feed-based full-content or summary extraction.

```bash
python3 extracting-news/method2/extract.py
```

Use `--limit 5` to extract only the first five input URLs.

Reads `extracting-urls/news_urls.json` and writes:

```text
extracting-news/method2/output/articles.json
extracting-news/method2/output/errors.json
extracting-news/method2/output/markdown/
```

This method matches article URLs back to RSS/Atom route entries. Full feed body
fields such as `content:encoded` are high confidence; summary-only feed entries
are retained as low confidence when they contain enough useful text.

## Extraction Logic

This method does not fetch the article page itself. Instead, it uses the feed
route that originally produced the article URL.

The script:

1. Reads `extracting-urls/news_urls.json`.
2. Keeps only rows whose `route_type` or `route_url` indicates RSS/Atom/feed.
3. Fetches each unique feed URL.
4. Parses RSS `<item>` and Atom `<entry>` records.
5. Matches feed entries back to the article URLs.
6. Extracts title, published date, author, categories, and body content from the
   feed entry.

It prefers full body fields:

```text
content:encoded
atom:content
```

If those are missing, it falls back to summary fields:

```text
description
atom:summary
```

The body HTML from the feed is converted to clean text before validation and
Markdown output.

## Confidence

`high` means the feed entry contained a likely full body. `low` means only a
summary was available, but it was still useful enough to keep.

## Strengths And Weaknesses

This method is excellent when publishers expose full article HTML in feeds,
especially WordPress-style feeds. It is weak for feeds that only publish short
summaries, and it cannot extract pages that were discovered from normal HTML
listing pages instead of feeds.
