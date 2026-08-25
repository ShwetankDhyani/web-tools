import { NextRequest, NextResponse } from "next/server";
import { cookies } from "next/headers";
import {
  addProduct,
  listProducts,
  scrapeProduct,
  sessionUser,
} from "@/lib/prices";
import { validatePublicHttpUrl } from "@/lib/security";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function GET() {
  const jar = await cookies();
  const user = sessionUser(jar.get("wt_session")?.value);
  if (!user) {
    return NextResponse.json({ error: "Sign in required." }, { status: 401 });
  }
  return NextResponse.json({ items: listProducts(user.username) });
}

export async function POST(req: NextRequest) {
  const jar = await cookies();
  const user = sessionUser(jar.get("wt_session")?.value);
  if (!user) {
    return NextResponse.json({ error: "Sign in required." }, { status: 401 });
  }

  const body = await req.json().catch(() => ({}));
  const url = String(body.url ?? "").trim();
  const targetPrice = Number(body.targetPrice);
  let name = String(body.name ?? "").trim();
  let currentPrice =
    body.currentPrice != null && body.currentPrice !== ""
      ? Number(body.currentPrice)
      : null;
  let currency = String(body.currency ?? "").trim();

  if (!url) {
    return NextResponse.json({ error: "Product URL is required." }, { status: 400 });
  }
  const bad = await validatePublicHttpUrl(url);
  if (bad) {
    return NextResponse.json({ error: bad }, { status: 400 });
  }
  if (!Number.isFinite(targetPrice) || targetPrice <= 0) {
    return NextResponse.json({ error: "Enter a valid target price." }, { status: 400 });
  }

  if (!name || currentPrice == null || !currency) {
    const scraped = await scrapeProduct(url);
    name = name || scraped.name;
    if (currentPrice == null) currentPrice = scraped.price;
    currency = currency || scraped.currency;
  }

  const product = addProduct(user.username, {
    url,
    name,
    currentPrice: Number.isFinite(currentPrice as number) ? (currentPrice as number) : null,
    targetPrice,
    currency: currency || "$",
  });

  return NextResponse.json({ item: product });
}
