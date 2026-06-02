import { createHash } from "node:crypto";
import { mkdir, writeFile } from "node:fs/promises";
import { join } from "node:path";
import type {
  ArticleRecord,
  ExtractionError,
  ToMarkdownOptions,
  UrlRow,
} from "../types.js";
import { composeBodyMarkdown, htmlToPlainText } from "./dom.js";
import type { Candidate } from "./types.js";
import {
  cleanText,
  domainFromUrl,
  markdownYamlValue,
  nowIso,
  occurrences,
  paragraphText,
  uniqueStrings,
} from "./utils.js";

const DEFAULT_MIN_BODY_CHARS = 280;
const DEFAULT_SHORT_FEED_CHARS = 120;
const BOILERPLATE_PHRASES = [
  "kupsiseid",
  "küpsiseid",
  "cookie",
  "noustun",
  "nõustun",
  "avaleht",
  "juurdepääsetavus",
  "privaatsuspoliitika",
];

export function articleRecord(
  row: UrlRow,
  finalUrl: string,
  candidate: Candidate,
): ArticleRecord {
  const title =
    cleanText(candidate.title) || cleanText(row.discovered_title) || null;
  const lead = cleanText(candidate.lead) || null;
  const bodyText = paragraphText(
    candidate.bodyText || htmlToPlainText(candidate.bodyHtml || "", finalUrl),
  );
  const bodyMarkdown =
    candidate.bodyMarkdown ||
    composeBodyMarkdown(
      title,
      lead,
      candidate.bodyHtml || null,
      bodyText,
      finalUrl,
    );
  const paragraphs = bodyText.split(/\n{2,}/).filter((part) => part.trim());
  const sourceDomain =
    cleanText(row.source_domain) ||
    domainFromUrl(finalUrl) ||
    domainFromUrl(row.url);

  return {
    url: row.url,
    final_url: finalUrl !== row.url ? finalUrl : null,
    source_domain: sourceDomain,
    source_name: cleanText(row.source_name) || null,
    title,
    lead,
    body_text: bodyText,
    body_markdown: bodyMarkdown,
    author: cleanText(candidate.author) || null,
    published_at:
      cleanText(candidate.publishedAt) ||
      cleanText(row.discovered_published_at) ||
      null,
    modified_at: cleanText(candidate.modifiedAt) || null,
    tags: uniqueStrings(candidate.tags || []),
    language: cleanText(candidate.language) || "et",
    images: uniqueStrings(candidate.images || []),
    links: uniqueStrings(candidate.links || []),
    extraction_method: candidate.extractionMethod,
    extraction_confidence: candidate.extractionConfidence,
    content_length_chars: bodyText.length,
    paragraph_count: paragraphs.length,
    retrieved_at: nowIso(),
  };
}

export function acceptRecord(
  record: ArticleRecord,
  options: ToMarkdownOptions,
): [boolean, string | null] {
  const problem = validationError(record, options);
  if (
    problem === "body_too_short" &&
    record.extraction_method === "feed_based_full_content" &&
    record.extraction_confidence === "low" &&
    record.body_text.length >=
      (options.allowShortFeedBodyChars ?? DEFAULT_SHORT_FEED_CHARS)
  ) {
    return [true, null];
  }
  return [problem === null, problem];
}

export function recordToMarkdown(record: ArticleRecord): string {
  const frontmatter: Record<string, unknown> = {
    title: record.title,
    source: record.source_name,
    source_domain: record.source_domain,
    url: record.url,
    final_url: record.final_url,
    published_at: record.published_at,
    author: record.author,
    language: record.language,
    tags: record.tags,
    extraction_method: record.extraction_method,
    extraction_confidence: record.extraction_confidence,
    retrieved_at: record.retrieved_at,
  };
  const yaml = Object.entries(frontmatter)
    .map(([key, value]) => `${key}: ${markdownYamlValue(value)}`)
    .join("\n");
  return `---\n${yaml}\n---\n\n${record.body_markdown || ""}\n`;
}

export async function writeMarkdownFile(
  record: ArticleRecord,
  outputDir: string,
): Promise<string> {
  await mkdir(outputDir, { recursive: true });
  const path = join(outputDir, `${safeSlug(record.url, record.title)}.md`);
  await writeFile(path, recordToMarkdown(record), "utf8");
  return path;
}

export function safeSlug(url: string, title?: string | null): string {
  const parsed = new URL(url);
  const pathStem = parsed.pathname.split("/").filter(Boolean).at(-1);
  const stem = (title || pathStem || parsed.hostname).toLowerCase();
  const slug = stem
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-|-$/g, "")
    .slice(0, 70);
  const digest = createHash("sha1").update(url).digest("hex").slice(0, 10);
  return `${slug || "article"}-${digest}`;
}

export function errorRecord(
  row: UrlRow,
  errorTypeValue: string,
  message: string,
  method: string,
): ExtractionError {
  return {
    url: row.url,
    source_domain: cleanText(row.source_domain) || null,
    error_type: errorTypeValue,
    message,
    extraction_method: method,
    retrieved_at: nowIso(),
  };
}

function validationError(
  record: ArticleRecord,
  options: ToMarkdownOptions,
): string | null {
  if (!record.url) {
    return "missing_url";
  }
  if (!record.title) {
    return "missing_title";
  }
  if (!record.body_text) {
    return "empty_body";
  }
  if (
    record.body_text.length < (options.minBodyChars ?? DEFAULT_MIN_BODY_CHARS)
  ) {
    return "body_too_short";
  }
  const lowered = record.body_text.toLowerCase();
  const boilerplateHits = BOILERPLATE_PHRASES.reduce(
    (count, phrase) => count + occurrences(lowered, phrase),
    0,
  );
  if (boilerplateHits && boilerplateHits * 80 > record.body_text.length) {
    return "boilerplate_dominant";
  }
  if (!["high", "medium", "low"].includes(record.extraction_confidence)) {
    return "invalid_confidence";
  }
  return null;
}
