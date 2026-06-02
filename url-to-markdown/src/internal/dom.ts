import { JSDOM } from "jsdom";
import TurndownService from "turndown";
import turndownPluginGfm from "turndown-plugin-gfm";
import {
  absoluteUrl,
  cleanText,
  cssEscape,
  normalizeMarkdown,
  paragraphText,
  startsWithHeading,
  uniqueStrings,
} from "./utils.js";

export function parseDocument(html: string, url: string): Document {
  return new JSDOM(html, { url }).window.document;
}

export function composeBodyMarkdown(
  title: string | null,
  lead: string | null,
  bodyHtml: string | null,
  bodyText: string,
  baseUrl: string,
): string {
  const contentMarkdown = normalizeMarkdown(
    bodyHtml ? htmlToMarkdown(bodyHtml, baseUrl) : bodyText,
  );
  const parts: string[] = [];
  if (title && !startsWithHeading(contentMarkdown, title)) {
    parts.push(`# ${title}`);
  }
  if (lead && !contentMarkdown.toLowerCase().includes(lead.toLowerCase())) {
    parts.push(`**${lead}**`);
  }
  if (contentMarkdown) {
    parts.push(contentMarkdown);
  }
  return normalizeMarkdown(parts.join("\n\n"));
}

export function htmlToMarkdown(html: string, baseUrl: string): string {
  const document = parseDocument(html, baseUrl);
  absolutizeMedia(document, baseUrl);
  const turndown = new TurndownService({
    headingStyle: "atx",
    codeBlockStyle: "fenced",
    bulletListMarker: "-",
    emDelimiter: "*",
    strongDelimiter: "**",
  });
  turndown.use(turndownPluginGfm.gfm);
  turndown.remove(["script", "style", "noscript"]);
  return normalizeMarkdown(turndown.turndown(document.body || document));
}

export function htmlToPlainText(html: string, baseUrl: string): string {
  if (!html) {
    return "";
  }
  const document = parseDocument(html, baseUrl);
  return textOfElement(document.body);
}

export function textFromNodes(nodes: Element[]): string {
  return nodes
    .map((node) => textOfElement(node))
    .filter(Boolean)
    .join("\n\n");
}

export function htmlFromNodes(nodes: Element[]): string {
  return nodes
    .map((node) => node.innerHTML)
    .filter(Boolean)
    .join("\n");
}

export function textOf(node: Element | null): string | null {
  const text = cleanText(node?.textContent);
  return text || null;
}

export function textOfElement(node: Element | null): string {
  if (!node) {
    return "";
  }
  const chunks: string[] = [];
  const walk = (current: Node) => {
    if (current.nodeType === current.TEXT_NODE) {
      chunks.push(current.textContent || "");
      return;
    }
    if (current.nodeType !== current.ELEMENT_NODE) {
      return;
    }
    const element = current as Element;
    const tag = element.tagName.toLowerCase();
    if (["script", "style", "noscript", "svg"].includes(tag)) {
      return;
    }
    if (tag === "br") {
      chunks.push("\n");
      return;
    }
    if (tag === "li") {
      chunks.push("\n- ");
    }
    for (const child of Array.from(element.childNodes)) {
      walk(child);
    }
    if (isBlockTag(tag)) {
      chunks.push("\n\n");
    }
  };
  walk(node);
  return paragraphText(chunks.join(""));
}

export function selectAll(document: Document, selector: string): Element[] {
  return Array.from(document.querySelectorAll(selector));
}

export function innerHtml(node: Element | null): string {
  return node?.innerHTML || "";
}

export function attr(node: Element | null, name: string): string | null {
  return node?.getAttribute(name) || null;
}

export function metaContent(
  document: Document,
  ...names: string[]
): string | null {
  for (const name of names) {
    const node =
      document.querySelector(`meta[property="${cssEscape(name)}"]`) ||
      document.querySelector(`meta[name="${cssEscape(name)}"]`) ||
      document.querySelector(`meta[itemprop="${cssEscape(name)}"]`);
    const content = node?.getAttribute("content");
    if (content) {
      return cleanText(content);
    }
  }
  return null;
}

export function mediaFromHtml(
  html: string,
  baseUrl: string,
): { images: string[]; links: string[] } {
  return mediaFromDocument(
    parseDocument(html, baseUrl),
    baseUrl,
    "img[src]",
    "a[href]",
  );
}

export function mediaFromDocument(
  document: Document,
  baseUrl: string,
  imageSelector: string,
  linkSelector: string,
): { images: string[]; links: string[] } {
  const images = selectAll(document, imageSelector)
    .map((node) => absoluteUrl(node.getAttribute("src"), baseUrl))
    .filter((url): url is string => Boolean(url));
  const links = selectAll(document, linkSelector)
    .map((node) => absoluteUrl(node.getAttribute("href"), baseUrl))
    .filter((url): url is string => Boolean(url));
  return { images: uniqueStrings(images), links: uniqueStrings(links) };
}

function absolutizeMedia(document: Document, baseUrl: string): void {
  for (const node of selectAll(document, "a[href]")) {
    const href = absoluteUrl(node.getAttribute("href"), baseUrl);
    if (href) {
      node.setAttribute("href", href);
    }
  }
  for (const node of selectAll(document, "img[src]")) {
    const src = absoluteUrl(node.getAttribute("src"), baseUrl);
    if (src) {
      node.setAttribute("src", src);
    }
  }
}

function isBlockTag(tag: string): boolean {
  return [
    "article",
    "aside",
    "blockquote",
    "div",
    "figcaption",
    "figure",
    "footer",
    "h1",
    "h2",
    "h3",
    "h4",
    "h5",
    "h6",
    "header",
    "li",
    "main",
    "p",
    "section",
    "table",
    "ul",
    "ol",
  ].includes(tag);
}
