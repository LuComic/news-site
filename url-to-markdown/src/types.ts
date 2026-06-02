export type ExtractionConfidence = "high" | "medium" | "low";

export interface UrlRow {
  url: string;
  source_domain?: string | null;
  source_name?: string | null;
  route_url?: string | null;
  route_type?: string | null;
  discovered_title?: string | null;
  discovered_published_at?: string | null;
  [key: string]: unknown;
}

export type UrlInput = string | URL | UrlRow;

export interface ToMarkdownOptions {
  timeoutMs?: number;
  retries?: number;
  retryDelayMs?: number;
  headers?: Record<string, string>;
  userAgent?: string;
  fetch?: typeof fetch;
  includeFrontmatter?: boolean;
  minBodyChars?: number;
  allowShortFeedBodyChars?: number;
}

export interface ArticleRecord {
  url: string;
  final_url?: string | null;
  source_domain?: string | null;
  source_name?: string | null;
  title: string | null;
  lead: string | null;
  body_text: string;
  body_markdown: string;
  author: string | null;
  published_at: string | null;
  modified_at: string | null;
  tags: string[];
  language: string | null;
  images: string[];
  links: string[];
  extraction_method: string;
  extraction_confidence: ExtractionConfidence;
  content_length_chars: number;
  paragraph_count: number;
  retrieved_at: string;
  fallback_chain?: string[];
  combined_extraction_method?: string;
}

export interface ExtractionError {
  url?: string | null;
  source_domain?: string | null;
  error_type: string;
  message: string;
  extraction_method: string;
  retrieved_at: string;
}

export interface ArticleExtractionResult {
  record: ArticleRecord | null;
  errors: ExtractionError[];
}

export interface UrlConversionStatus {
  url: string;
  row: UrlRow;
  success: boolean;
  article_index: number | null;
  article_title: string | null;
  article_method: string | null;
  errors: ExtractionError[];
}

export interface FailedUrlConversion {
  url: string;
  row: UrlRow;
  last_error: ExtractionError | null;
  errors: ExtractionError[];
}

export interface BatchExtractionStats {
  total_urls: number;
  successful_urls: number;
  failed_urls: number;
  success_rate: number;
  failed_error_count: number;
  attempt_error_count: number;
  started_at: string;
  finished_at: string;
}

export interface BatchExtractionResult {
  stats: BatchExtractionStats;
  urls: UrlConversionStatus[];
  successful_urls: string[];
  failed_urls: FailedUrlConversion[];
  articles: ArticleRecord[];
  errors: ExtractionError[];
  all_attempt_errors: ExtractionError[];
}
