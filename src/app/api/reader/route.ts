import { NextRequest, NextResponse } from "next/server";
import { clientKey, rateLimitExceeded, validatePublicHttpUrl } from "@/lib/security";
import { extractArticle } from "@/lib/reader";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function POST(req: NextRequest) {
  const ip = req.headers.get("x-forwarded-for")?.split(",")[0]?.trim() ?? "local";
  if (rateLimitExceeded(clientKey(ip, "reader"), 15, 60)) {
    return NextResponse.json(
      { error: "Too many requests. Please wait a moment." },
      { status: 429 },
    );
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

  try {
    const article = await extractArticle(url);
    return NextResponse.json(article);
  } catch (err) {
    const message =
      err instanceof Error
        ? err.message
        : "Could not extract a readable article.";
    return NextResponse.json({ error: message }, { status: 400 });
  }
}
