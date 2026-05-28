# Method 1

Deterministic site-family selector extraction.

```bash
python3 extracting-news/method1/extract.py
```

Use `--limit 5` to extract only the first five input URLs.

Reads `extracting-urls/news_urls.json` and writes:

```text
extracting-news/method1/output/articles.json
extracting-news/method1/output/errors.json
extracting-news/method1/output/markdown/
```

This is the high-confidence path for known public-sector CMS families such as
VPortal/Drupal, Police/Rescue Nuxt SSR pages, Statistikaamet, and WordPress-like
article pages.

## Extraction Logic

This method fetches each article page and chooses a selector set based on
`source_domain`.

For VPortal/Drupal public-sector sites, it looks for the Drupal news article
structure first:

```text
article.node--type-news
.field--name-field-lead-text
.field--name-field-news-components .field--name-field-text-section-content
.field--name-field-news-authors
.field--name-field-keywords
.card-text.vp-date
```

The title normally comes from `h1`, the lead from the lead-text field, and the
body from the news component text sections. Authors, tags, dates, images, and
links are collected from nearby structured fields when available.

For Police and Rescue sites, it uses the Nuxt SSR page structure:

```text
main#maincontent
main#maincontent .content h1
main#maincontent time[datetime]
main#maincontent section.componentized
```

For Statistikaamet, it uses the article node fields:

```text
article.node--type-article
h1.page-title
.field--name-field-summary-news
.field--name-body
```

For unknown or WordPress-like pages, it falls back to common article selectors
such as `article.post`, `.entry-content`, `article`, and `main`.

## Confidence

`high` means a known site-family body selector matched. `medium` means the
method had to fall back to a broader article/main selector.

## Strengths And Weaknesses

This method is usually the cleanest for known government CMS layouts because it
extracts from exact content fields instead of guessing. It is less foolproof for
new domains or redesigned sites, because unfamiliar markup may not match the
known selector families.
