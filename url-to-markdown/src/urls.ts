import newsUrlRows from "../../extracting-urls/news_urls.json" with { type: "json" };
import type { UrlRow } from "./types.js";

export const urlRows = newsUrlRows as UrlRow[];

export const urls = urlRows.map((row) => row.url);

export function getUrlRow(url: string): UrlRow | undefined {
  return urlRows.find((row) => row.url === url);
}
