import type {
  ArticleRecord,
  BatchExtractionResult,
  ExtractionError,
  ToMarkdownOptions,
  UrlRow,
} from "./types.js";
import { tryExtractArticle, writeMarkdownFile } from "./extractor.js";
import { errorRecord } from "./internal/records.js";
import { errorMessage, errorType, nowIso } from "./internal/utils.js";

export interface BatchExtractionOptions extends ToMarkdownOptions {
  outputDir?: string;
  onProgress?: (event: {
    index: number;
    total: number;
    row: UrlRow;
  }) => void | Promise<void>;
  onResult?: (event: {
    index: number;
    total: number;
    row: UrlRow;
    record: ArticleRecord | null;
    errors: ExtractionError[];
  }) => void | Promise<void>;
}

export async function extractArticles(
  rows: UrlRow[],
  options: BatchExtractionOptions = {},
): Promise<BatchExtractionResult> {
  const startedAt = nowIso();
  const articles: ArticleRecord[] = [];
  const errors: ExtractionError[] = [];
  const allAttemptErrors: ExtractionError[] = [];
  const urls: BatchExtractionResult["urls"] = [];
  const failedUrls: BatchExtractionResult["failed_urls"] = [];
  const successfulUrls: string[] = [];

  for (const [index, row] of rows.entries()) {
    await options.onProgress?.({ index: index + 1, total: rows.length, row });

    try {
      const result = await tryExtractArticle(row, options);
      allAttemptErrors.push(...result.errors);

      if (result.record) {
        const articleIndex = articles.length;
        articles.push(result.record);
        successfulUrls.push(row.url);
        if (options.outputDir) {
          await writeMarkdownFile(result.record, options.outputDir);
        }
        urls.push({
          url: row.url,
          row,
          success: true,
          article_index: articleIndex,
          article_title: result.record.title,
          article_method: result.record.extraction_method,
          errors: result.errors,
        });
        await options.onResult?.({
          index: index + 1,
          total: rows.length,
          row,
          record: result.record,
          errors: result.errors,
        });
      } else {
        errors.push(...result.errors);
        failedUrls.push({
          url: row.url,
          row,
          last_error: result.errors.at(-1) || null,
          errors: result.errors,
        });
        urls.push({
          url: row.url,
          row,
          success: false,
          article_index: null,
          article_title: null,
          article_method: null,
          errors: result.errors,
        });
        await options.onResult?.({
          index: index + 1,
          total: rows.length,
          row,
          record: null,
          errors: result.errors,
        });
      }
    } catch (error) {
      const extractionError = errorRecord(
        row,
        errorType(error),
        errorMessage(error),
        "typescript_url_to_markdown_batch",
      );
      errors.push(extractionError);
      allAttemptErrors.push(extractionError);
      failedUrls.push({
        url: row.url,
        row,
        last_error: extractionError,
        errors: [extractionError],
      });
      urls.push({
        url: row.url,
        row,
        success: false,
        article_index: null,
        article_title: null,
        article_method: null,
        errors: [extractionError],
      });
      await options.onResult?.({
        index: index + 1,
        total: rows.length,
        row,
        record: null,
        errors: [extractionError],
      });
    }
  }

  const finishedAt = nowIso();
  return {
    stats: {
      total_urls: rows.length,
      successful_urls: articles.length,
      failed_urls: failedUrls.length,
      success_rate: rows.length ? articles.length / rows.length : 0,
      failed_error_count: errors.length,
      attempt_error_count: allAttemptErrors.length,
      started_at: startedAt,
      finished_at: finishedAt,
    },
    urls,
    successful_urls: successfulUrls,
    failed_urls: failedUrls,
    articles,
    errors,
    all_attempt_errors: allAttemptErrors,
  };
}
