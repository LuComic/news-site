export function validateHttpUrl(url: string): void {
  const parsed = new URL(url);
  if (!["http:", "https:"].includes(parsed.protocol)) {
    throw new TypeError(`Only http/https URLs are supported: ${url}`);
  }
}

export function cleanText(value: unknown): string {
  return String(value ?? "")
    .replace(/\s+/g, " ")
    .trim();
}

export function paragraphText(value: string): string {
  return value
    .split(/[\r\n]+/)
    .map((line) => cleanText(line))
    .filter(Boolean)
    .join("\n\n");
}

export function normalizeMarkdown(value: string): string {
  return value
    .replace(/\r\n/g, "\n")
    .replace(/[ \t]+\n/g, "\n")
    .replace(/\n{3,}/g, "\n\n")
    .trim();
}

export function absoluteUrl(value: unknown, baseUrl: string): string | null {
  const raw = cleanText(value);
  if (!raw) {
    return null;
  }
  try {
    return new URL(raw, baseUrl).toString();
  } catch {
    return null;
  }
}

export function domainFromUrl(url: string): string | null {
  try {
    return new URL(url).hostname.replace(/^www\./, "").toLowerCase();
  } catch {
    return null;
  }
}

export function startsWithHeading(markdown: string, title: string): boolean {
  const firstLine = markdown.split("\n").find((line) => line.trim());
  if (!firstLine) {
    return false;
  }
  const normalizedHeading = firstLine
    .replace(/^#+\s*/, "")
    .trim()
    .toLowerCase();
  return normalizedHeading === title.trim().toLowerCase();
}

export function uniqueStrings(values: string[]): string[] {
  return Array.from(
    new Set(values.map((value) => cleanText(value)).filter(Boolean)),
  );
}

export function markdownYamlValue(value: unknown): string {
  if (value === undefined || value === null || value === "") {
    return "null";
  }
  return JSON.stringify(value);
}

export function asArray(value: unknown): unknown[] {
  if (Array.isArray(value)) {
    return value;
  }
  return value === undefined || value === null ? [] : [value];
}

export function objectValue(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : {};
}

export function getPath(value: unknown, path: string[]): unknown {
  let current = value;
  for (const part of path) {
    const obj = objectValue(current);
    current = obj[part];
    if (current === undefined || current === null) {
      return undefined;
    }
  }
  return current;
}

export function textValue(value: unknown): string {
  if (typeof value === "string" || typeof value === "number") {
    return cleanText(String(value));
  }
  const obj = objectValue(value);
  return (
    cleanText(obj["#cdata"]) ||
    cleanText(obj["#text"]) ||
    cleanText(obj._text) ||
    cleanText(obj.value)
  );
}

export function occurrences(value: string, pattern: string): number {
  if (!pattern) {
    return 0;
  }
  return value.split(pattern).length - 1;
}

export function cssEscape(value: string): string {
  return value.replace(/\\/g, "\\\\").replace(/"/g, '\\"');
}

export function errorType(error: unknown): string {
  return error instanceof Error
    ? error.name || error.constructor.name
    : "Error";
}

export function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}

export function nowIso(): string {
  return new Date().toISOString();
}

export function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}
