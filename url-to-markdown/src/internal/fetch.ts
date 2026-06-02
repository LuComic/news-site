import { detect } from "chardet";
import iconv from "iconv-lite";
import type { ToMarkdownOptions } from "../types.js";
import type { FetchResult } from "./types.js";
import { sleep, validateHttpUrl } from "./utils.js";

const DEFAULT_USER_AGENT =
  "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 " +
  "(KHTML, like Gecko) Chrome/125.0 Safari/537.36";
const DEFAULT_TIMEOUT_MS = 25_000;
const DEFAULT_RETRIES = 1;

export async function fetchUrl(
  url: string,
  options: ToMarkdownOptions,
): Promise<FetchResult> {
  validateHttpUrl(url);
  const fetchImpl = options.fetch || fetch;
  const retries = options.retries ?? DEFAULT_RETRIES;
  let lastError: unknown;

  for (let attempt = 0; attempt <= retries; attempt += 1) {
    const controller = new AbortController();
    const timeout = setTimeout(
      () => controller.abort(),
      options.timeoutMs ?? DEFAULT_TIMEOUT_MS,
    );
    try {
      const response = await fetchImpl(url, {
        headers: {
          "User-Agent": options.userAgent || DEFAULT_USER_AGENT,
          Accept:
            "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
          "Accept-Language": "et-EE,et;q=0.9,en;q=0.8",
          ...options.headers,
        },
        redirect: "follow",
        signal: controller.signal,
      });
      if (!response.ok) {
        throw new Error(
          `HTTP ${response.status} ${response.statusText}`.trim(),
        );
      }
      const body = Buffer.from(await response.arrayBuffer());
      const contentType = response.headers.get("content-type") || "";
      return {
        finalUrl: response.url || url,
        contentType,
        body,
        text: decodeBody(body, contentType),
      };
    } catch (error) {
      lastError = error;
      if (attempt >= retries) {
        break;
      }
      await sleep((options.retryDelayMs ?? 350) * (attempt + 1));
    } finally {
      clearTimeout(timeout);
    }
  }

  throw lastError instanceof Error ? lastError : new Error(String(lastError));
}

function decodeBody(body: Buffer, contentType: string): string {
  const charset =
    charsetFromContentType(contentType) ||
    charsetFromHtml(body) ||
    detect(body) ||
    "utf-8";
  const normalized = normalizeCharset(charset);
  if (iconv.encodingExists(normalized)) {
    return iconv.decode(body, normalized);
  }
  return body.toString("utf8");
}

function charsetFromContentType(contentType: string): string | null {
  const match = /charset=([^;]+)/i.exec(contentType);
  return match ? match[1].trim().replace(/^["']|["']$/g, "") : null;
}

function charsetFromHtml(body: Buffer): string | null {
  const prefix = body.subarray(0, 4096).toString("latin1");
  return (
    /<meta[^>]+charset=["']?\s*([^"'\s/>]+)/i.exec(prefix)?.[1] ||
    /<meta[^>]+content=["'][^"']*charset=([^"';\s]+)/i.exec(prefix)?.[1] ||
    null
  );
}

function normalizeCharset(charset: string): string {
  const lowered = charset.toLowerCase().replace(/^["']|["']$/g, "");
  if (lowered === "utf8") {
    return "utf-8";
  }
  return lowered;
}
