#!/usr/bin/env node
import { readFile, rm, writeFile } from "node:fs/promises";
import { parseArgs } from "node:util";
import {
  createAuditReport,
  extractArticle,
  extractArticles,
  recordToMarkdown,
  toMarkdown,
  writeMarkdownFile,
} from "./index.js";
import type { ToMarkdownOptions, UrlRow } from "./index.js";

const { values, positionals } = parseArgs({
  allowPositionals: true,
  options: {
    input: { type: "string", short: "i" },
    "output-dir": { type: "string", short: "o" },
    "articles-output": { type: "string" },
    "errors-output": { type: "string" },
    report: { type: "string" },
    limit: { type: "string" },
    "timeout-ms": { type: "string" },
    retries: { type: "string" },
    "no-frontmatter": { type: "boolean" },
    json: { type: "boolean" },
    help: { type: "boolean", short: "h" },
  },
});

if (values.help) {
  usage(0);
}

const options: ToMarkdownOptions = {
  timeoutMs: numberOption(values["timeout-ms"]),
  retries: numberOption(values.retries),
  includeFrontmatter: values["no-frontmatter"] ? false : undefined,
};

try {
  if (values.input) {
    await runBatch(values.input, options);
  } else {
    await runSingle(positionals[0], options);
  }
} catch (error) {
  console.error(error instanceof Error ? error.message : String(error));
  process.exitCode = 1;
}

async function runSingle(url: string | undefined, options: ToMarkdownOptions) {
  if (!url) {
    usage(1);
  }
  if (values["output-dir"]) {
    const record = await extractArticle(url, options);
    const path = await writeMarkdownFile(record, values["output-dir"]);
    console.error(`Wrote ${path}`);
    return;
  }
  const markdown = await toMarkdown(url, options);
  process.stdout.write(markdown);
}

async function runBatch(inputPath: string, options: ToMarkdownOptions) {
  const raw = await readFile(inputPath, "utf8");
  const rows = JSON.parse(raw) as UrlRow[];
  if (!Array.isArray(rows)) {
    throw new Error(`Expected a JSON array in ${inputPath}`);
  }
  const limit = numberOption(values.limit);
  const selectedRows = limit === undefined ? rows : rows.slice(0, limit);
  console.error(`Loaded ${selectedRows.length} URLs from ${inputPath}`);
  if (values["output-dir"]) {
    await rm(values["output-dir"], { recursive: true, force: true });
  }
  const result = await extractArticles(selectedRows, {
    ...options,
    outputDir: values["output-dir"],
    onProgress: ({ index, total, row }) => {
      console.error(`[${index}/${total}] Checking ${row.url}`);
    },
    onResult: ({ record, errors }) => {
      if (record) {
        console.error(
          `  SUCCESS ${record.extraction_method} (${record.content_length_chars} chars)`,
        );
        return;
      }
      const lastAttempt = errors.at(-1);
      console.error(
        "  ERROR " +
          `${lastAttempt?.extraction_method || "unknown"}: ` +
          `${lastAttempt?.error_type || "unknown"} - ` +
          `${lastAttempt?.message || "No extraction attempts recorded"}`,
      );
    },
  });
  const audit = createAuditReport(result, inputPath);

  if (values["articles-output"]) {
    await writeFile(
      values["articles-output"],
      JSON.stringify(result.articles, null, 2),
      "utf8",
    );
  }
  if (values["errors-output"]) {
    await writeFile(
      values["errors-output"],
      JSON.stringify(result.errors, null, 2),
      "utf8",
    );
  }
  if (values.report) {
    await writeFile(values.report, JSON.stringify(audit, null, 2), "utf8");
  }
  if (values.json) {
    process.stdout.write(`${JSON.stringify(audit, null, 2)}\n`);
  }
  if (
    !values.json &&
    !values["output-dir"] &&
    !values["articles-output"] &&
    !values["errors-output"] &&
    !values.report
  ) {
    process.stdout.write(result.articles.map(recordToMarkdown).join("\n\n"));
  }
  console.error("");
  console.error("Extraction audit summary");
  console.error(`  Total URLs: ${audit.summary.total_urls}`);
  console.error(`  Successes: ${audit.summary.successful_extractions}`);
  console.error(`  Errors: ${audit.summary.failed_extractions}`);
  console.error(`  Success rate: ${audit.summary.success_rate_percent}%`);
  console.error(`  Failure rate: ${audit.summary.failure_rate_percent}%`);
  if (values.report) {
    console.error(`  Report: ${values.report}`);
  }
}

function numberOption(value: unknown): number | undefined {
  if (value === undefined) {
    return undefined;
  }
  const number = Number(value);
  if (!Number.isFinite(number)) {
    throw new Error(`Expected a number, got ${String(value)}`);
  }
  return number;
}

function usage(exitCode: number): never {
  console.error(`Usage:
  url-to-markdown <url> [--output-dir output/markdowns]
  url-to-markdown --input extracting-urls/news_urls.json --output-dir output/markdowns --articles-output output/articles.json --errors-output output/errors.json --report output/extraction_audit.json

Common npm scripts:
  npm run audit:sample       Check first 5 URLs and print success rate without markdown output
  npm run audit              Check all URLs and print success rate without markdown output
  npm run convert:sample     Convert first 5 Python-discovered URLs and write markdown output
  npm run convert -- --json  Return audit JSON to stdout
  npm run convert -- --limit 50
  npm run convert            Convert all Python-discovered URLs

Options:
  -i, --input <path>          JSON array from the Python URL extractor
  -o, --output-dir <path>     Directory for markdown files
      --articles-output <p>   Write article records JSON
      --errors-output <p>     Write extraction errors JSON
      --report <p>            Write audit report JSON matching audit_extraction_success.py
      --limit <n>             Process only the first n rows
      --timeout-ms <n>        Fetch timeout in milliseconds
      --retries <n>           Fetch retry count
      --no-frontmatter        Return/write body markdown only for single URL stdout
      --json                  For batch mode, return all URL statuses and stats as JSON
`);
  process.exit(exitCode);
}
