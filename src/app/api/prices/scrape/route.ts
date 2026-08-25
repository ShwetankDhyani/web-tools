import { NextRequest, NextResponse } from "next/server";
import { scrapeProduct } from "@/lib/prices";
import { clientKey, rateLimitExceeded, validatePublicHttpUrl } from "@/lib/security";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function POST(req: NextRequest) {
  const ip = req.headers.get("x-forwarded-for")?.split(",")[0]?.trim() ?? "local";
  if (rateLimitExceeded(clientKey(ip, "scrape"), 20, 60)) {
    return NextResponse.json({ error: "Too many requests." }, { status: 429 });
  }

  const body = await req.json().catch(() => ({}));
  const url = String(body.url ?? "").trim();
  if (!url) {
    return NextResponse.json({ error: "URL is required" }, { status: 400 });
  }
  const bad = await validatePublicHttpUrl(url);
  if (bad) {
    return NextResponse.json({ error: bad }, { status: 400 });
  }

  const data = await scrapeProduct(url);
  return NextResponse.json(data);
}
