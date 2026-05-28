# Method 4

Readability-style boilerplate removal extraction.

```bash
python3 extracting-news/method4/extract.py
```

Use `--limit 5` to extract only the first five input URLs.

Reads `extracting-urls/news_urls.json` and writes:

```text
extracting-news/method4/output/articles.json
extracting-news/method4/output/errors.json
extracting-news/method4/output/markdown/
```

This is the second generic baseline. It uses `readability-lxml` to isolate the
likely article block, then records Open Graph/meta metadata where present.

## Extraction Logic

This method fetches each article page and sends the HTML to `readability-lxml`,
a Readability-style boilerplate removal library. Readability scores blocks of
HTML and chooses the section that most resembles an article body.

The script extracts:

```text
Document.short_title() -> title
Document.summary() -> likely article HTML
summary text -> body_text
article/main links -> links
article/main images -> images
```

It also reads common metadata from the original page:

```text
og:title
og:description
description
article:author
author
article:published_time
article:modified_time
date
```

The selected article HTML is converted into clean text, then the shared output
layer builds Markdown and validates the result.

## Confidence

This method records `medium` confidence. It is a generic readability heuristic,
so it can work across many domains, but it does not know the exact structure of
any specific government CMS.

## Strengths And Weaknesses

This method is useful when Method 1 selectors do not match and when Trafilatura
needs a second opinion. It is good at removing page chrome, but it can sometimes
select too much or too little when the page has unusual layout blocks, related
content sections, or heavily componentized markup.
