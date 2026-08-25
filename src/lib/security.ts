import { isIP } from "node:net";
import { lookup } from "node:dns/promises";

const BLOCKED_HOSTS = new Set([
  "localhost",
  "metadata.google.internal",
  "metadata.goog",
  "kubernetes.default",
  "kubernetes.default.svc",
]);

function ipIsUnsafe(ip: string): boolean {
  const version = isIP(ip);
  if (!version) return true;

  if (version === 4) {
    const parts = ip.split(".").map(Number);
    const [a, b] = parts;
    if (a === 10) return true;
    if (a === 127) return true;
    if (a === 0) return true;
    if (a === 169 && b === 254) return true;
    if (a === 172 && b >= 16 && b <= 31) return true;
    if (a === 192 && b === 168) return true;
    if (a === 100 && b >= 64 && b <= 127) return true;
    if (a >= 224) return true;
    return false;
  }

  const normalized = ip.toLowerCase();
  if (normalized === "::1" || normalized === "::") return true;
  if (normalized.startsWith("fc") || normalized.startsWith("fd")) return true;
  if (normalized.startsWith("fe80")) return true;
  if (normalized.startsWith("ff")) return true;
  return false;
}

export async function isBlockedHost(hostname: string): Promise<boolean> {
  const host = hostname.replace(/^\[|\]$/g, "").toLowerCase();
  if (!host) return true;
  if (BLOCKED_HOSTS.has(host) || host.endsWith(".local") || host.endsWith(".internal")) {
    return true;
  }
  if (isIP(host)) return ipIsUnsafe(host);

  try {
    const results = await lookup(host, { all: true });
    return results.some((r) => ipIsUnsafe(r.address));
  } catch {
    return true;
  }
}

export async function validatePublicHttpUrl(
  url: string,
  maxLen = 2048,
): Promise<string | null> {
  if (!url || url.length > maxLen) return "Invalid URL.";
  let parsed: URL;
  try {
    parsed = new URL(url.trim());
  } catch {
    return "Invalid URL.";
  }
  if (parsed.protocol !== "http:" && parsed.protocol !== "https:") {
    return "Only http and https URLs are allowed.";
  }
  if (!parsed.hostname) return "Invalid URL.";
  if (parsed.username || parsed.password) {
    return "URLs with credentials are not allowed.";
  }
  if (await isBlockedHost(parsed.hostname)) {
    return "That host is not allowed.";
  }
  return null;
}

type Bucket = number[];
const rateBuckets = new Map<string, Bucket>();

export function rateLimitExceeded(
  key: string,
  limit: number,
  windowSec: number,
): boolean {
  const now = Date.now();
  const windowMs = windowSec * 1000;
  const bucket = (rateBuckets.get(key) ?? []).filter((t) => now - t < windowMs);
  if (bucket.length >= limit) {
    rateBuckets.set(key, bucket);
    return true;
  }
  bucket.push(now);
  rateBuckets.set(key, bucket);
  return false;
}

export function clientKey(ip: string | null | undefined, suffix: string): string {
  return `${ip || "unknown"}:${suffix}`;
}
