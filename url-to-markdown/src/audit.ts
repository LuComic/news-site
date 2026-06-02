import type {
  ArticleRecord,
  BatchExtractionResult,
  ExtractionError,
} from "./types.js";

export interface CompactAttempt {
  extraction_method?: string | null;
  error_type?: string | null;
  message?: string | null;
}

export interface AuditSuccess {
  url: string;
  source_domain?: string | null;
  title?: string | null;
  extraction_method: string;
  extraction_confidence?: string | null;
  content_length_chars: number;
  paragraph_count: number;
  fallback_chain?: string[];
}

export interface AuditError {
  url: string;
  source_domain?: string | null;
  last_error_type?: string | null;
  last_message?: string | null;
  attempts: CompactAttempt[];
}

export interface ExtractionAuditReport {
  summary: {
    urls_input: string;
    total_urls: number;
    successful_extractions: number;
    failed_extractions: number;
    success_rate_percent: number;
    failure_rate_percent: number;
    successes_by_method: Record<string, number>;
    successes_by_source_domain: Record<string, number>;
  };
  successes: AuditSuccess[];
  errors: AuditError[];
}

export function createAuditReport(
  result: BatchExtractionResult,
  urlsInput: string,
): ExtractionAuditReport {
  const successes = result.articles.map(auditSuccess);
  const errors = result.failed_urls.map((failed) => {
    const lastAttempt = failed.errors.at(-1);
    return {
      url: failed.url,
      source_domain: failed.row.source_domain,
      last_error_type: lastAttempt?.error_type,
      last_message: lastAttempt?.message,
      attempts: compactAttempts(failed.errors),
    };
  });
  return {
    summary: {
      urls_input: urlsInput,
      total_urls: result.stats.total_urls,
      successful_extractions: successes.length,
      failed_extractions: errors.length,
      success_rate_percent: percentage(
        successes.length,
        result.stats.total_urls,
      ),
      failure_rate_percent: percentage(errors.length, result.stats.total_urls),
      successes_by_method: countBy(
        successes,
        (success) => success.extraction_method,
      ),
      successes_by_source_domain: countBy(
        successes,
        (success) => success.source_domain || "unknown",
      ),
    },
    successes,
    errors,
  };
}

export function compactAttempts(attempts: ExtractionError[]): CompactAttempt[] {
  return attempts.map((attempt) => ({
    extraction_method: attempt.extraction_method,
    error_type: attempt.error_type,
    message: attempt.message,
  }));
}

function auditSuccess(record: ArticleRecord): AuditSuccess {
  return {
    url: record.url,
    source_domain: record.source_domain,
    title: record.title,
    extraction_method: record.extraction_method || "unknown",
    extraction_confidence: record.extraction_confidence,
    content_length_chars: record.content_length_chars,
    paragraph_count: record.paragraph_count,
    fallback_chain: record.fallback_chain,
  };
}

function percentage(count: number, total: number): number {
  return total ? Math.round((count / total) * 10000) / 100 : 0;
}

function countBy<T>(
  values: T[],
  keyFn: (value: T) => string,
): Record<string, number> {
  const counts = new Map<string, number>();
  for (const value of values) {
    const key = keyFn(value) || "unknown";
    counts.set(key, (counts.get(key) || 0) + 1);
  }
  return Object.fromEntries(
    Array.from(counts.entries()).sort((left, right) => right[1] - left[1]),
  );
}
