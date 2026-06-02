import { XMLParser } from "fast-xml-parser";
import type { ToMarkdownOptions, UrlRow } from "../types.js";
import { htmlToPlainText } from "./dom.js";
import { fetchUrl } from "./fetch.js";
import type { Candidate } from "./types.js";
import {
  absoluteUrl,
  asArray,
  cleanText,
  getPath,
  objectValue,
  textValue,
  uniqueStrings,
} from "./utils.js";

type FeedEntry = {
  url: string;
  title: string;
  bodyHtml: string;
  isFull: boolean;
  publishedAt: string | null;
  author: string | null;
  tags: string[];
  feedUrl: string;
};

export function isFeedBacked(row: UrlRow): boolean {
  const routeUrl = cleanText(row.route_url);
  return (
    row.route_type === "rss" ||
    row.route_type === "atom" ||
    /(rss|feed|atom)/i.test(routeUrl)
  );
}

export async function feedExtract(
  row: UrlRow,
  options: ToMarkdownOptions,
): Promise<Candidate> {
  const feedUrl = cleanText(row.route_url);
  if (!feedUrl) {
    throw new Error("No feed route_url found for URL row");
  }
  const fetched = await fetchUrl(feedUrl, options);
  const entries = feedEntries(fetched.text, fetched.finalUrl);
  const target = normalizeMatchUrl(row.url);
  const entry = entries.find(
    (candidate) => normalizeMatchUrl(candidate.url) === target,
  );
  if (!entry) {
    throw new Error("No matching RSS/Atom entry found for article URL");
  }
  const bodyText = htmlToPlainText(entry.bodyHtml, entry.feedUrl);
  return {
    title: entry.title,
    lead: entry.isFull ? null : bodyText.slice(0, 280),
    bodyHtml: entry.bodyHtml,
    bodyText,
    author: entry.author,
    publishedAt: entry.publishedAt,
    tags: entry.tags,
    links: [entry.feedUrl],
    extractionMethod: "feed_based_full_content",
    extractionConfidence:
      entry.isFull && bodyText.length > 800 ? "high" : "low",
  };
}

function feedEntries(xmlText: string, feedUrl: string): FeedEntry[] {
  const parser = new XMLParser({
    ignoreAttributes: false,
    attributeNamePrefix: "@_",
    cdataPropName: "#cdata",
    textNodeName: "#text",
    trimValues: true,
  });
  const parsed = parser.parse(xmlText) as Record<string, unknown>;
  const rssItems = asArray(
    getPath(parsed, ["rss", "channel", "item"]) ||
      getPath(parsed, ["rdf:RDF", "item"]),
  );
  const atomEntries = asArray(getPath(parsed, ["feed", "entry"]));

  return [
    ...rssItems.map((item) => rssEntry(item, feedUrl)),
    ...atomEntries.map((entry) => atomEntry(entry, feedUrl)),
  ].filter((entry) => entry.url);
}

function rssEntry(value: unknown, feedUrl: string): FeedEntry {
  const item = objectValue(value);
  const content = textValue(item["content:encoded"]);
  const summary = textValue(item.description);
  const bodyHtml = content || summary;
  return {
    url: absoluteUrl(textValue(item.link), feedUrl) || "",
    title: textValue(item.title),
    bodyHtml,
    isFull: Boolean(content && content.length > summary.length),
    publishedAt: textValue(item.pubDate) || null,
    author: textValue(item["dc:creator"]) || textValue(item.author) || null,
    tags: categoriesFrom(item.category),
    feedUrl,
  };
}

function atomEntry(value: unknown, feedUrl: string): FeedEntry {
  const entry = objectValue(value);
  const links = asArray(entry.link);
  const alternate = links.find((link) => {
    const obj = objectValue(link);
    return !obj["@_rel"] || obj["@_rel"] === "alternate";
  });
  const linkObject = objectValue(alternate || links[0]);
  const link =
    textValue(alternate || links[0]) || cleanText(linkObject["@_href"]);
  const content = textValue(entry.content);
  const summary = textValue(entry.summary);
  const bodyHtml = content || summary;
  return {
    url: absoluteUrl(link, feedUrl) || "",
    title: textValue(entry.title),
    bodyHtml,
    isFull: Boolean(content && content.length > summary.length),
    publishedAt:
      textValue(entry.published) ||
      textValue(entry.updated) ||
      textValue(entry["dc:date"]) ||
      null,
    author:
      textValue(getPath(entry, ["author", "name"])) ||
      textValue(entry.author) ||
      null,
    tags: categoriesFrom(entry.category),
    feedUrl,
  };
}

function categoriesFrom(value: unknown): string[] {
  return uniqueStrings(
    asArray(value)
      .map((entry) => {
        const obj = objectValue(entry);
        return textValue(entry) || cleanText(obj["@_term"]);
      })
      .filter((tag): tag is string => Boolean(tag)),
  );
}

function normalizeMatchUrl(url: string): string {
  return url.split("#", 1)[0].replace(/\/+$/g, "");
}
