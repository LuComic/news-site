import { extractFromHtml } from "@extractus/article-extractor";
import { Readability } from "@mozilla/readability";
import { JSDOM } from "jsdom";
import type {
  ExtractionConfidence,
  ToMarkdownOptions,
  UrlRow,
} from "../types.js";
import {
  attr,
  htmlFromNodes,
  htmlToPlainText,
  innerHtml,
  mediaFromDocument,
  mediaFromHtml,
  metaContent,
  parseDocument,
  selectAll,
  textFromNodes,
  textOf,
  textOfElement,
} from "./dom.js";
import type { Candidate, HtmlExtractor } from "./types.js";
import {
  absoluteUrl,
  cleanText,
  domainFromUrl,
  uniqueStrings,
} from "./utils.js";

const VPORTAL_DOMAINS = new Set([
  "valitsus.ee",
  "fin.ee",
  "justdigi.ee",
  "kliimaministeerium.ee",
  "keskkonnaamet.ee",
  "konkurentsiamet.ee",
  "transpordiamet.ee",
]);

type ExtractusArticle = {
  title?: string;
  description?: string;
  image?: string;
  author?: string;
  content?: string;
  published?: string;
  source?: string;
  links?: unknown[];
};

export const deterministicSelectorExtract: HtmlExtractor = Object.assign(
  deterministicSelectorExtractImpl,
  { methodName: "deterministic_site_family_selectors" },
);

export const extractusExtract: HtmlExtractor = Object.assign(
  extractusExtractImpl,
  {
    methodName: "extractus_article_extractor",
  },
);

export const readabilityExtract: HtmlExtractor = Object.assign(
  readabilityExtractImpl,
  { methodName: "readability_boilerplate_removal" },
);

function deterministicSelectorExtractImpl(
  row: UrlRow,
  html: string,
  finalUrl: string,
  _options: ToMarkdownOptions,
): Candidate {
  const document = parseDocument(html, finalUrl);
  const domain = (cleanText(row.source_domain) || domainFromUrl(finalUrl) || "")
    .replace(/^www\./, "")
    .toLowerCase();
  let title: string | null = null;
  let lead: string | null = null;
  let bodyText = "";
  let bodyHtml = "";
  let author: string | null = null;
  let publishedAt: string | null = null;
  let modifiedAt: string | null = null;
  let tags: string[] = [];
  let confidence: ExtractionConfidence = "medium";

  if (VPORTAL_DOMAINS.has(domain)) {
    const article =
      document.querySelector("article.node--type-news") ||
      document.querySelector("main");
    const titleNode =
      document.querySelector("h1") || document.querySelector(".page-title");
    const leadNode = document.querySelector(".field--name-field-lead-text");
    let bodyNodes = selectAll(
      document,
      ".field--name-field-news-components .field--name-field-text-section-content",
    );
    if (!bodyNodes.length) {
      bodyNodes = selectAll(
        document,
        ".field--name-body, .field--name-field-text-section-content",
      );
    }
    const authorNode = document.querySelector(
      ".field--name-field-news-authors",
    );
    const dateNode = document.querySelector(
      ".card-text.vp-date time, .card-text.vp-date, time[datetime]",
    );
    title = textOf(titleNode);
    lead = textOf(leadNode);
    bodyText = textFromNodes(bodyNodes) || textOfElement(article);
    bodyHtml = htmlFromNodes(bodyNodes) || innerHtml(article);
    author = textOf(authorNode);
    publishedAt = attr(dateNode, "datetime") || textOf(dateNode);
    tags = selectAll(
      document,
      ".field--name-field-keywords a, .field--name-field-keywords .field__item",
    )
      .map((node) => textOf(node))
      .filter((tag): tag is string => Boolean(tag));
    confidence = bodyNodes.length ? "high" : "medium";
  } else if (domain === "politsei.ee" || domain === "rescue.ee") {
    const main = document.querySelector("main#maincontent");
    const titleNode = document.querySelector(
      "main#maincontent .content h1, main#maincontent h1",
    );
    const timeNode = document.querySelector("main#maincontent time[datetime]");
    const bodyNode =
      document.querySelector("main#maincontent section.componentized") || main;
    title = textOf(titleNode);
    bodyText = textOfElement(bodyNode);
    bodyHtml = innerHtml(bodyNode);
    publishedAt = attr(timeNode, "datetime");
    confidence = bodyNode ? "high" : "medium";
  } else if (domain === "stat.ee") {
    const article =
      document.querySelector("article.node--type-article") ||
      document.querySelector("main");
    const titleNode = document.querySelector("h1.page-title, h1");
    const leadNode = document.querySelector(".field--name-field-summary-news");
    const bodyNode = document.querySelector(".field--name-body");
    title = textOf(titleNode);
    lead = textOf(leadNode);
    bodyText = textOfElement(bodyNode) || textOfElement(article);
    bodyHtml = innerHtml(bodyNode) || innerHtml(article);
    confidence = bodyNode ? "high" : "medium";
  } else {
    const titleNode = document.querySelector(
      "article.post h1, h1.entry-title, h1",
    );
    const bodyNode = document.querySelector(
      ".entry-content, article .content, article, main",
    );
    title = textOf(titleNode) || metaContent(document, "og:title");
    bodyText = textOfElement(bodyNode);
    bodyHtml = innerHtml(bodyNode);
  }

  title = title || metaContent(document, "og:title", "twitter:title");
  publishedAt =
    publishedAt || metaContent(document, "article:published_time", "date");
  modifiedAt = modifiedAt || metaContent(document, "article:modified_time");

  const media = mediaFromDocument(
    document,
    finalUrl,
    "article img[src], main img[src]",
    "article a[href], main a[href]",
  );
  return {
    title,
    lead,
    bodyText,
    bodyHtml,
    author,
    publishedAt,
    modifiedAt,
    tags,
    language: document.documentElement.getAttribute("lang"),
    images: media.images,
    links: media.links,
    extractionMethod: "deterministic_site_family_selectors",
    extractionConfidence: confidence,
  };
}

async function extractusExtractImpl(
  _row: UrlRow,
  html: string,
  finalUrl: string,
  _options: ToMarkdownOptions,
): Promise<Candidate> {
  const article = (await extractFromHtml(html, finalUrl, {
    descriptionLengthThreshold: 120,
    contentLengthThreshold: 200,
  })) as ExtractusArticle | null;
  if (!article?.content) {
    throw new Error("Article extractor returned no content");
  }
  const media = mediaFromHtml(article.content, finalUrl);
  const image = absoluteUrl(article.image, finalUrl);
  return {
    title: article.title,
    lead: article.description,
    bodyHtml: article.content,
    bodyText: htmlToPlainText(article.content, finalUrl),
    author: article.author,
    publishedAt: article.published,
    images: uniqueStrings([...(image ? [image] : []), ...media.images]),
    links: media.links,
    extractionMethod: "extractus_article_extractor",
    extractionConfidence: "medium",
  };
}

function readabilityExtractImpl(
  _row: UrlRow,
  html: string,
  finalUrl: string,
  _options: ToMarkdownOptions,
): Candidate {
  const dom = new JSDOM(html, { url: finalUrl });
  const document = dom.window.document.cloneNode(true) as Document;
  const parsed = new Readability(document, {
    charThreshold: 200,
  }).parse();
  if (!parsed?.content && !parsed?.textContent) {
    throw new Error("Readability returned no content");
  }
  const media = mediaFromHtml(parsed.content || "", finalUrl);
  return {
    title: parsed.title,
    lead: parsed.excerpt,
    bodyHtml: parsed.content,
    bodyText: parsed.textContent,
    author: parsed.byline,
    publishedAt: parsed.publishedTime,
    language: parsed.lang,
    images: media.images,
    links: media.links,
    extractionMethod: "readability_boilerplate_removal",
    extractionConfidence: "medium",
  };
}
