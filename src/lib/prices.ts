import {
  existsSync,
  mkdirSync,
  readFileSync,
  renameSync,
  writeFileSync,
} from "node:fs";
import { join } from "node:path";
import { nanoid } from "nanoid";
import type { PriceUser, TrackedProduct } from "./price-types";

export type { PriceUser, TrackedProduct };

type OtpRecord = {
  username: string;
  code: string;
  createdAt: string;
};

type StoreShape = {
  products: TrackedProduct[];
  users: PriceUser[];
  otps: OtpRecord[];
  sessions: Record<string, { username: string; createdAt: string }>;
};

const DATA_DIR = join(process.cwd(), "data", "prices");
const STORE_PATH = join(DATA_DIR, "store.json");

function ensure() {
  mkdirSync(DATA_DIR, { recursive: true });
  if (!existsSync(STORE_PATH)) {
    const empty: StoreShape = { products: [], users: [], otps: [], sessions: {} };
    writeFileSync(STORE_PATH, JSON.stringify(empty, null, 2));
  }
}

function readStore(): StoreShape {
  ensure();
  try {
    return JSON.parse(readFileSync(STORE_PATH, "utf8")) as StoreShape;
  } catch {
    return { products: [], users: [], otps: [], sessions: {} };
  }
}

function writeStore(store: StoreShape) {
  ensure();
  const tmp = `${STORE_PATH}.tmp`;
  writeFileSync(tmp, JSON.stringify(store, null, 2));
  renameSync(tmp, STORE_PATH);
}

export function getDemoMode(): boolean {
  return process.env.PRICE_TRACKER_DEMO !== "0";
}

export function listProducts(username: string): TrackedProduct[] {
  return readStore().products.filter((p) => p.username === username);
}

export function addProduct(
  username: string,
  input: {
    url: string;
    name: string;
    currentPrice: number | null;
    targetPrice: number;
    currency: string;
  },
): TrackedProduct {
  const store = readStore();
  const product: TrackedProduct = {
    id: nanoid(10),
    url: input.url,
    name: input.name,
    currentPrice: input.currentPrice,
    targetPrice: input.targetPrice,
    currency: input.currency,
    username,
    lastChecked: input.currentPrice != null ? new Date().toISOString() : null,
    notified: false,
    createdAt: new Date().toISOString(),
    priceHistory:
      input.currentPrice != null
        ? [{ at: new Date().toISOString(), price: input.currentPrice }]
        : [],
    errorCount: 0,
    lastError: "",
  };
  store.products.push(product);
  writeStore(store);
  return product;
}

export function deleteProduct(username: string, id: string): boolean {
  const store = readStore();
  const before = store.products.length;
  store.products = store.products.filter(
    (p) => !(p.id === id && p.username === username),
  );
  writeStore(store);
  return store.products.length < before;
}

export function updateProduct(
  username: string,
  id: string,
  patch: Partial<Pick<TrackedProduct, "targetPrice" | "name" | "currentPrice" | "lastChecked" | "priceHistory" | "notified" | "lastError" | "errorCount">>,
): TrackedProduct | null {
  const store = readStore();
  const idx = store.products.findIndex((p) => p.id === id && p.username === username);
  if (idx < 0) return null;
  store.products[idx] = { ...store.products[idx], ...patch };
  writeStore(store);
  return store.products[idx];
}

export function createOtp(username: string): { code: string; demo: boolean } {
  const store = readStore();
  const code = String(Math.floor(100000 + Math.random() * 900000));
  store.otps = store.otps.filter((o) => o.username !== username.toLowerCase());
  store.otps.push({
    username: username.toLowerCase(),
    code,
    createdAt: new Date().toISOString(),
  });
  writeStore(store);
  return { code, demo: getDemoMode() };
}

export function verifyOtp(username: string, code: string): string | null {
  const store = readStore();
  const record = store.otps.find((o) => o.username === username.toLowerCase());
  if (!record) return null;
  const age = Date.now() - new Date(record.createdAt).getTime();
  if (age > 10 * 60 * 1000) return null;
  if (record.code !== code.trim()) return null;

  const sessionId = nanoid(24);
  store.sessions[sessionId] = {
    username: username.toLowerCase(),
    createdAt: new Date().toISOString(),
  };
  store.otps = store.otps.filter((o) => o.username !== username.toLowerCase());

  if (!store.users.some((u) => u.username === username.toLowerCase())) {
    const isAdmin =
      store.users.length === 0 ||
      username.toLowerCase() === (process.env.ADMIN_USERNAME || "").toLowerCase();
    store.users.push({
      username: username.toLowerCase(),
      createdAt: new Date().toISOString(),
      isAdmin,
    });
  }
  writeStore(store);
  return sessionId;
}

export function sessionUser(sessionId: string | undefined): PriceUser | null {
  if (!sessionId) return null;
  const store = readStore();
  const session = store.sessions[sessionId];
  if (!session) return null;
  return store.users.find((u) => u.username === session.username) ?? null;
}

export function destroySession(sessionId: string | undefined) {
  if (!sessionId) return;
  const store = readStore();
  delete store.sessions[sessionId];
  writeStore(store);
}

export function currencyFromUrl(url: string): string {
  try {
    const host = new URL(url).hostname.toLowerCase();
    if (host.includes(".in") || host.endsWith("flipkart.com")) return "₹";
    if (host.includes(".co.uk")) return "£";
    if (host.includes(".de") || host.includes(".fr") || host.includes(".es")) return "€";
    return "$";
  } catch {
    return "$";
  }
}

/** Lightweight public-page price extraction via JSON-LD / meta tags. */
export async function scrapeProduct(url: string): Promise<{
  name: string;
  price: number | null;
  currency: string;
}> {
  const currency = currencyFromUrl(url);
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 15000);
  try {
    const res = await fetch(url, {
      signal: controller.signal,
      headers: {
        "User-Agent":
          "Mozilla/5.0 (compatible; WebToolsWiki/2.0; +https://webtools.wiki)",
        Accept: "text/html",
      },
      redirect: "follow",
    });
    if (!res.ok) {
      return { name: guessName(url), price: null, currency };
    }
    const html = await res.text();
    const name =
      matchMeta(html, "og:title") ||
      matchTag(html, "title") ||
      guessName(url);

    let price: number | null = null;
    let detectedCurrency = currency;

    const ldBlocks = [...html.matchAll(/<script[^>]*type=["']application\/ld\+json["'][^>]*>([\s\S]*?)<\/script>/gi)];
    for (const block of ldBlocks) {
      try {
        const data = JSON.parse(block[1]);
        const nodes = Array.isArray(data) ? data : [data];
        for (const node of nodes) {
          const offers = node.offers ?? node.Offers;
          const offer = Array.isArray(offers) ? offers[0] : offers;
          if (offer?.price != null) {
            price = Number(offer.price);
            if (offer.priceCurrency) {
              detectedCurrency = symbolFor(offer.priceCurrency) || detectedCurrency;
            }
          }
          if (node["@type"] === "Product" && node.name && name === guessName(url)) {
            // prefer product name
          }
        }
      } catch {
        /* ignore bad JSON-LD */
      }
    }

    if (price == null) {
      const metaPrice =
        matchMeta(html, "product:price:amount") ||
        matchMeta(html, "og:price:amount");
      if (metaPrice) price = Number(metaPrice);
    }

    return {
      name: decodeEntities(name).slice(0, 200),
      price: Number.isFinite(price as number) ? (price as number) : null,
      currency: detectedCurrency,
    };
  } catch {
    return { name: guessName(url), price: null, currency };
  } finally {
    clearTimeout(timer);
  }
}

function matchMeta(html: string, property: string): string | null {
  const re = new RegExp(
    `<meta[^>]*(?:property|name)=["']${property}["'][^>]*content=["']([^"']+)["']`,
    "i",
  );
  const re2 = new RegExp(
    `<meta[^>]*content=["']([^"']+)["'][^>]*(?:property|name)=["']${property}["']`,
    "i",
  );
  return html.match(re)?.[1] ?? html.match(re2)?.[1] ?? null;
}

function matchTag(html: string, tag: string): string | null {
  const m = html.match(new RegExp(`<${tag}[^>]*>([^<]+)</${tag}>`, "i"));
  return m?.[1]?.trim() ?? null;
}

function guessName(url: string): string {
  try {
    const u = new URL(url);
    const part = u.pathname.split("/").filter(Boolean).pop() || u.hostname;
    return decodeURIComponent(part).replace(/[-_]+/g, " ").slice(0, 80);
  } catch {
    return "Tracked product";
  }
}

function symbolFor(code: string): string {
  const map: Record<string, string> = {
    USD: "$",
    INR: "₹",
    EUR: "€",
    GBP: "£",
    JPY: "¥",
  };
  return map[code.toUpperCase()] ?? code;
}

function decodeEntities(text: string): string {
  return text
    .replace(/&amp;/g, "&")
    .replace(/&lt;/g, "<")
    .replace(/&gt;/g, ">")
    .replace(/&quot;/g, '"')
    .replace(/&#39;/g, "'");
}
