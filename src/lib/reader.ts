import { Readability } from "@mozilla/readability";
import { parseHTML } from "linkedom";
import sanitizeHtml from "sanitize-html";
import { validatePublicHttpUrl } from "./security";

const BROWSER_HEADERS: Record<string, string> = {
  "User-Agent":
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
  Accept: "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
  "Accept-Language": "en-US,en;q=0.5",
  Referer: "https://www.google.com/",
  DNT: "1",
  "Upgrade-Insecure-Requests": "1",
  "Cache-Control": "no-cache",
};

const ALLOWED_TAGS = [
  "p", "br", "hr", "pre", "code", "blockquote",
  "h1", "h2", "h3", "h4", "h5", "h6",
  "ul", "ol", "li", "dl", "dt", "dd",
  "table", "thead", "tbody", "tfoot", "tr", "th", "td",
  "figure", "figcaption", "img", "picture", "source",
  "div", "span", "section", "article", "header", "footer",
  "strong", "em", "b", "i", "u", "s", "sub", "sup", "mark",
  "a", "abbr", "cite", "q", "time",
];

export function sanitizeArticleHtml(html: string): string {
  if (!html) return "";
  return sanitizeHtml(html, {
    allowedTags: ALLOWED_TAGS,
    allowedAttributes: {
      "*": ["class", "title", "lang", "dir"],
      a: ["href", "title", "rel", "target"],
      img: ["src", "alt", "title", "width", "height", "loading", "srcset", "sizes"],
      source: ["src", "srcset", "type", "media", "sizes"],
      td: ["colspan", "rowspan"],
      th: ["colspan", "rowspan", "scope"],
      time: ["datetime"],
    },
    allowedSchemes: ["http", "https", "mailto"],
  });
}

function stripTracking(url: string): string {
  try {
    const u = new URL(url);
    const drop = new Set([
      "utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content",
      "ref", "fbclid", "gclid", "mc_cid", "mc_eid", "mod", "from", "source",
    ]);
    for (const key of [...u.searchParams.keys()]) {
      if (drop.has(key.toLowerCase())) u.searchParams.delete(key);
    }
    return u.toString();
  } catch {
    return url;
  }
}

async function fetchHtml(url: string): Promise<string> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 20000);
  try {
    const res = await fetch(url, {
      headers: BROWSER_HEADERS,
      redirect: "follow",
      signal: controller.signal,
    });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const finalUrl = res.url;
    const bad = await validatePublicHttpUrl(finalUrl);
    if (bad) throw new Error("Redirected to a blocked host.");
    const contentType = res.headers.get("content-type") ?? "";
    if (!contentType.includes("text/html") && !contentType.includes("application/xhtml")) {
      // still try — some CDNs omit types
    }
    return await res.text();
  } finally {
    clearTimeout(timer);
  }
}

export type ReaderArticle = {
  title: string;
  byline: string;
  excerpt: string;
  siteName: string;
  content: string;
  wordCount: number;
  sourceUrl: string;
  favicon: string;
};

export async function extractArticle(rawUrl: string): Promise<ReaderArticle> {
  const url = stripTracking(rawUrl.trim());
  const bad = await validatePublicHttpUrl(url);
  if (bad) throw new Error(bad);

  const html = await fetchHtml(url);
  const { document } = parseHTML(html);
  const reader = new Readability(document, { charThreshold: 200 });
  const article = reader.parse();
  if (!article) {
    throw new Error(
      "Could not extract a readable article. The page may require a browser, or the publisher blocked automated access.",
    );
  }

  const text = (article.textContent ?? "").trim();
  if (!article.content || text.length < 80) {
    throw new Error(
      "Could not extract a readable article. The page may require a browser, or the publisher blocked automated access.",
    );
  }

  const host = new URL(url).hostname.replace(/^www\./, "");
  const words = text.split(/\s+/).filter(Boolean).length;

  return {
    title: article.title || "Untitled",
    byline: article.byline || "",
    excerpt: article.excerpt || "",
    siteName: article.siteName || host,
    content: sanitizeArticleHtml(article.content),
    wordCount: words,
    sourceUrl: url,
    favicon: `https://www.google.com/s2/favicons?domain=${encodeURIComponent(host)}&sz=64`,
  };
}
