import type {
  ExtractionConfidence,
  ToMarkdownOptions,
  UrlRow,
} from "../types.js";

export interface Candidate {
  title?: string | null;
  lead?: string | null;
  bodyText?: string | null;
  bodyHtml?: string | null;
  bodyMarkdown?: string | null;
  author?: string | null;
  publishedAt?: string | null;
  modifiedAt?: string | null;
  tags?: string[];
  language?: string | null;
  images?: string[];
  links?: string[];
  extractionMethod: string;
  extractionConfidence: ExtractionConfidence;
}

export type HtmlExtractor = ((
  row: UrlRow,
  html: string,
  finalUrl: string,
  options: ToMarkdownOptions,
) => Candidate | Promise<Candidate>) & {
  methodName: string;
};

export interface FetchResult {
  finalUrl: string;
  contentType: string;
  body: Buffer;
  text: string;
}
