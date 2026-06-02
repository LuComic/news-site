import type {
  ArticleExtractionResult,
  ArticleRecord,
  ExtractionError,
  ToMarkdownOptions,
  UrlInput,
  UrlRow,
} from "./types.js";
import { feedExtract, isFeedBacked } from "./internal/feed.js";
import { fetchUrl } from "./internal/fetch.js";
import {
  acceptRecord,
  articleRecord,
  errorRecord,
  recordToMarkdown,
  safeSlug,
  writeMarkdownFile,
} from "./internal/records.js";
import {
  deterministicSelectorExtract,
  extractusExtract,
  readabilityExtract,
} from "./internal/site-extractors.js";
import type { HtmlExtractor } from "./internal/types.js";
import { errorMessage, errorType, validateHttpUrl } from "./internal/utils.js";

const COMBINED_METHOD = "typescript_url_to_markdown_fallback_extractor";

class ArticleExtractionError extends Error {
  readonly attempts: ExtractionError[];

  constructor(message: string, attempts: ExtractionError[]) {
    super(message);
    this.name = "ArticleExtractionError";
    this.attempts = attempts;
  }
}

export {
  ArticleExtractionError,
  recordToMarkdown,
  safeSlug,
  writeMarkdownFile,
};

export async function toMarkdown(
  input: UrlInput,
  options: ToMarkdownOptions = {},
): Promise<string> {
  const record = await extractArticle(input, options);
  if (options.includeFrontmatter === false) {
    return record.body_markdown;
  }
  return recordToMarkdown(record);
}

export async function extractArticle(
  input: UrlInput,
  options: ToMarkdownOptions = {},
): Promise<ArticleRecord> {
  const result = await tryExtractArticle(input, options);
  if (result.record) {
    return result.record;
  }
  const last = result.errors.at(-1);
  throw new ArticleExtractionError(
    last?.message || "No extractor returned a valid article",
    result.errors,
  );
}

export async function tryExtractArticle(
  input: UrlInput,
  options: ToMarkdownOptions = {},
): Promise<ArticleExtractionResult> {
  const row = normalizeInput(input);
  const attempts: ExtractionError[] = [];
  let html = "";
  let finalUrl = row.url;

  try {
    const fetched = await fetchUrl(row.url, options);
    html = fetched.text;
    finalUrl = fetched.finalUrl;
  } catch (error) {
    attempts.push(
      errorRecord(
        row,
        errorType(error),
        errorMessage(error),
        "fetch_article_html",
      ),
    );
  }

  if (html) {
    const extractors: HtmlExtractor[] = [
      deterministicSelectorExtract,
      extractusExtract,
      readabilityExtract,
    ];
    const extracted = await tryHtmlExtractors(
      row,
      html,
      finalUrl,
      options,
      attempts,
      extractors,
    );
    if (extracted) {
      return { record: extracted, errors: attempts };
    }
  }

  if (isFeedBacked(row)) {
    const extracted = await tryFeedExtractor(row, options, attempts);
    if (extracted) {
      return { record: extracted, errors: attempts };
    }
  }

  return { record: null, errors: attempts };
}

async function tryHtmlExtractors(
  row: UrlRow,
  html: string,
  finalUrl: string,
  options: ToMarkdownOptions,
  attempts: ExtractionError[],
  extractors: HtmlExtractor[],
): Promise<ArticleRecord | null> {
  for (const extractor of extractors) {
    try {
      const candidate = await extractor(row, html, finalUrl, options);
      const record = articleRecord(row, finalUrl, candidate);
      const [ok, problem] = acceptRecord(record, options);
      if (ok) {
        record.fallback_chain = [
          ...attempts.map((attempt) => attempt.extraction_method),
          `${candidate.extractionMethod}:success`,
        ];
        record.combined_extraction_method = COMBINED_METHOD;
        return record;
      }
      attempts.push(
        errorRecord(
          row,
          problem || "validation_failed",
          `${candidate.extractionMethod} validation failed: ${problem}`,
          candidate.extractionMethod,
        ),
      );
    } catch (error) {
      attempts.push(
        errorRecord(
          row,
          errorType(error),
          errorMessage(error),
          extractor.methodName,
        ),
      );
    }
  }
  return null;
}

async function tryFeedExtractor(
  row: UrlRow,
  options: ToMarkdownOptions,
  attempts: ExtractionError[],
): Promise<ArticleRecord | null> {
  try {
    const candidate = await feedExtract(row, options);
    const record = articleRecord(row, row.url, candidate);
    const [ok, problem] = acceptRecord(record, options);
    if (ok) {
      record.fallback_chain = [
        ...attempts.map((attempt) => attempt.extraction_method),
        "feed_based_full_content:success",
      ];
      record.combined_extraction_method = COMBINED_METHOD;
      return record;
    }
    attempts.push(
      errorRecord(
        row,
        problem || "validation_failed",
        `feed_based_full_content validation failed: ${problem}`,
        "feed_based_full_content",
      ),
    );
  } catch (error) {
    attempts.push(
      errorRecord(
        row,
        errorType(error),
        errorMessage(error),
        "feed_based_full_content",
      ),
    );
  }
  return null;
}

function normalizeInput(input: UrlInput): UrlRow {
  const row =
    typeof input === "string"
      ? { url: input }
      : input instanceof URL
        ? { url: input.toString() }
        : { ...input };
  if (!row.url || typeof row.url !== "string") {
    throw new TypeError(
      "Expected a URL string, URL object, or URL row with url",
    );
  }
  validateHttpUrl(row.url);
  return row;
}
