import { describe, expect, it } from "vitest";
import {
  recordToMarkdown,
  toMarkdown,
  tryExtractArticle,
} from "../src/index.js";
import type { ToMarkdownOptions, UrlRow } from "../src/index.js";

const longParagraph = [
  "This article body is intentionally long enough to pass validation.",
  "It has real sentence structure, enough distinct words, and no dominant boilerplate.",
  "The extractor should keep the meaningful paragraphs and ignore navigation.",
  "This mirrors the public-sector news article pages where body text can be nested in fields.",
].join(" ");

describe("url-to-markdown extractor", () => {
  it("uses deterministic public-sector selectors first", async () => {
    const row: UrlRow = {
      url: "https://valitsus.ee/uudised/important-update",
      source_domain: "valitsus.ee",
      source_name: "Government Office",
      discovered_title: "Important update",
    };
    const html = `<!doctype html>
      <html lang="et">
        <head><meta property="article:published_time" content="2026-01-01"></head>
        <body>
          <main>
            <article class="node--type-news">
              <h1>Important update</h1>
              <div class="field--name-field-lead-text">Short lead</div>
              <div class="field--name-field-news-components">
                <div class="field--name-field-text-section-content">
                  <p>${longParagraph}</p>
                  <p>${longParagraph}</p>
                </div>
              </div>
            </article>
          </main>
        </body>
      </html>`;

    const result = await tryExtractArticle(row, testOptions(html, row.url));

    expect(result.record?.extraction_method).toBe("deterministic_site_family_selectors");
    expect(result.record?.fallback_chain).toEqual([
      "deterministic_site_family_selectors:success",
    ]);
    expect(recordToMarkdown(result.record!)).toContain("# Important update");
  });

  it("returns markdown from the public toMarkdown(url) API", async () => {
    const url = "https://example.test/uudised/markdown-api";
    const html = `<!doctype html>
      <html>
        <head>
          <meta property="og:title" content="Markdown API">
          <meta name="description" content="Lead sentence">
        </head>
        <body>
          <article>
            <h1>Markdown API</h1>
            <p>${longParagraph}</p>
            <p><a href="/more">More info</a></p>
          </article>
        </body>
      </html>`;

    const markdown = await toMarkdown(url, testOptions(html, url));

    expect(markdown).toContain('title: "Markdown API"');
    expect(markdown).toContain("# Markdown API");
    expect(markdown).toContain("[More info](https://example.test/more)");
  });

  it("falls back to RSS/Atom content for feed-backed URL rows", async () => {
    const row: UrlRow = {
      url: "https://example.test/uudised/feed-story",
      source_domain: "example.test",
      route_url: "https://example.test/rss.xml",
      route_type: "rss",
    };
    const feedBody = `${longParagraph} ${longParagraph}`;
    const feed = `<?xml version="1.0" encoding="UTF-8"?>
      <rss version="2.0">
        <channel>
          <item>
            <title>Feed story</title>
            <link>${row.url}</link>
            <description><![CDATA[<p>${feedBody}</p>]]></description>
            <pubDate>Tue, 02 Jun 2026 10:00:00 GMT</pubDate>
          </item>
        </channel>
      </rss>`;
    const fetcher: typeof fetch = async (input) => {
      const requested = String(input);
      if (requested.endsWith("rss.xml")) {
        return new Response(feed, {
          status: 200,
          headers: { "content-type": "application/rss+xml; charset=utf-8" },
        });
      }
      return new Response("Missing", { status: 404, statusText: "Not Found" });
    };

    const result = await tryExtractArticle(row, {
      fetch: fetcher,
      retries: 0,
    });

    expect(result.record?.extraction_method).toBe("feed_based_full_content");
    expect(result.record?.title).toBe("Feed story");
  });
});

function testOptions(html: string, url: string): ToMarkdownOptions {
  return {
    retries: 0,
    minBodyChars: 120,
    fetch: async () =>
      new Response(html, {
        status: 200,
        headers: { "content-type": "text/html; charset=utf-8" },
      }),
    headers: { "x-test-url": url },
  };
}
