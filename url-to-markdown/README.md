# URL to Markdown

Node/TypeScript article extraction for the URL-to-markdown part of the news
pipeline.

The Python pipeline should still discover sources and article URLs. This package
only consumes an individual URL, or one row from `extracting-urls/news_urls.json`,
and returns article markdown.

## Install

```bash
cd url-to-markdown
npm install
npm run build
```

## Use From TypeScript

```ts
import { toMarkdown, extractArticle } from "@testing-news-site/url-to-markdown";

const markdown = await toMarkdown("https://example.ee/uudised/story");

const article = await extractArticle({
  url: "https://example.ee/uudised/story",
  source_domain: "example.ee",
  source_name: "Example source",
  route_url: "https://example.ee/rss.xml",
  route_type: "rss",
});
```

`toMarkdown(urlOrRow)` returns markdown with YAML frontmatter by default. Use
`extractArticle(urlOrRow)` when the backend needs the article metadata, fallback
chain, images, links, and validation fields before saving.

## Local URL Rows

For local/dev use, the Python URL output is importable directly:

```ts
import { toMarkdown } from "@testing-news-site/url-to-markdown";
import { urlRows, urls, getUrlRow } from "@testing-news-site/url-to-markdown/urls";

const markdown = await toMarkdown(urlRows[0]);
const sameMarkdown = await toMarkdown(urls[0]);
const row = getUrlRow(urls[0]);
```

In production, replace `urlRows[0]` with the row your DB returns. The extractor
does not care where the row came from.

## Audit Python URL Output

Commands ending in `:sample` process only the first 5 URL rows. Use the command
without `:sample` to process every URL, or pass `--limit` for a custom sample
size.

From the repository root:

```bash
npm --prefix url-to-markdown run audit:sample
```

For a larger sample:

```bash
npm --prefix url-to-markdown run audit -- --limit 50
```

For all discovered URLs:

```bash
npm --prefix url-to-markdown run audit
```

To make the CLI return full run data as JSON:

```bash
npm --prefix url-to-markdown --silent run audit:sample -- --json
```

That JSON matches `audit_extraction_success.py`: `summary`, compact
`successes`, and compact `errors`.

This does not run source discovery or URL discovery. It only reads already
discovered URL rows and writes an audit report:

```text
output/extraction_audit.json
```

## Convert Python URL Output

Commands ending in `:sample` also use the first 5 URL rows here.

Use this when you actually want markdown/article output:

```bash
npm --prefix url-to-markdown run convert
```

Conversion writes:

```text
output/articles.json
output/errors.json
output/extraction_audit.json
output/markdowns/
```

The CLI also prints:

```text
Loaded 5 URLs from ../extracting-urls/news_urls.json
[1/5] Checking https://example.ee/uudised/story
  SUCCESS deterministic_site_family_selectors (15522 chars)

Extraction audit summary
  Total URLs: 5
  Successes: 4
  Errors: 1
  Success rate: 80%
  Failure rate: 20%
  Report: ../output/extraction_audit.json
```

## Extraction Fallbacks

The extractor tries these methods in order. The first method that returns a
valid article wins.

1. Deterministic selectors for known Estonian public-sector site families.

   This is the most precise method. It checks the source domain and uses known
   HTML/CMS structures for sites such as `valitsus.ee`, `fin.ee`,
   `justdigi.ee`, `kliimaministeerium.ee`, `politsei.ee`, `rescue.ee`, and
   `stat.ee`. For example, VPortal-style pages usually keep lead text, article
   body sections, authors, dates, keywords, images, and links in predictable
   field classes. When those fields exist, this method avoids generic
   boilerplate removal and gives higher-confidence output.

2. `@extractus/article-extractor` on the already-fetched HTML.

   This is the first generic fallback. It receives the HTML that was already
   fetched by our code, extracts the main article content and metadata, then we
   convert the returned HTML/text into our article record shape. It is useful
   for domains that are not covered by deterministic selectors, or pages where
   the known selectors no longer match.

3. Mozilla Readability through `jsdom`.

   This is the second generic fallback. The HTML is loaded into a `jsdom`
   document and passed to Mozilla Readability, the same family of logic used for
   reader-mode extraction. It scores likely article containers, removes
   navigation/sidebar noise, and returns title, excerpt, byline, content,
   language, and published time when it can find them.

4. RSS/Atom content, only when the URL row has feed-backed `route_url` metadata.

   This is the final fallback and only applies to rows that came from an RSS or
   Atom route. The extractor fetches the original feed, finds the entry matching
   the article URL, and uses `content:encoded`, Atom content, or description
   HTML as the article body. It can save articles when the page itself fails,
   but feed summaries can be shorter, so successful feed extraction may have
   lower confidence.

Validation mirrors the Python extractor: missing title, empty/short body,
boilerplate dominance, and invalid confidence are rejected before a fallback is
accepted.
