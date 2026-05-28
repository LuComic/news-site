# Method 3

Generic article extraction with Trafilatura.

```bash
python3 extracting-news/method3/extract.py
```

Use `--limit 5` to extract only the first five input URLs.

Reads `extracting-urls/news_urls.json` and writes:

```text
extracting-news/method3/output/articles.json
extracting-news/method3/output/errors.json
extracting-news/method3/output/markdown/
```

Install dependencies first:

```bash
python3 -m pip install -r requirements.txt
```

## Extraction Logic

This method fetches each article page and passes the HTML to `trafilatura`.
Trafilatura is a general-purpose article extraction library that tries to detect
the main textual content while removing navigation, menus, footers, sidebars,
cookie banners, and other boilerplate.

The script asks Trafilatura for JSON output with metadata enabled. From that
result it maps:

```text
title -> title
description -> lead
text -> body_text
author -> author
date -> published_at
language -> language
categories -> tags
```

The shared output layer then builds Markdown, calculates content length and
paragraph count, and validates that the result has a title, URL, confidence, and
non-empty body.

## Confidence

This method currently records `medium` confidence. It is not tied to one known
CMS, so it is usually more flexible than Method 1, but it is still an algorithmic
guess rather than a site-specific extraction.

## Strengths And Weaknesses

This is the best single method for new domains and unknown layouts. It often
handles pages well even when their HTML structure changes. It may still miss
content on JavaScript-heavy pages, unusual templates, or pages where the article
body is split into complex components.
