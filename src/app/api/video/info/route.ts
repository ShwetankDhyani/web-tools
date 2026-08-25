import { NextRequest, NextResponse } from "next/server";
import { clientKey, rateLimitExceeded, validatePublicHttpUrl } from "@/lib/security";
import { downloadStore } from "@/lib/download-store";
import { fetchVideoInfo, ytDlpAvailable } from "@/lib/yt-dlp";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function POST(req: NextRequest) {
  const ip = req.headers.get("x-forwarded-for")?.split(",")[0]?.trim() ?? "local";
  if (rateLimitExceeded(clientKey(ip, "video-info"), 20, 60)) {
    return NextResponse.json(
      { error: "Too many requests. Please wait a moment." },
      { status: 429 },
    );
  }

  if (!ytDlpAvailable()) {
    return NextResponse.json(
      { error: "Video downloader is not configured on this server." },
      { status: 503 },
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
    downloadStore.cleanup();
    const info = await fetchVideoInfo(url);
    return NextResponse.json(info);
  } catch (err) {
    const message =
      err instanceof Error ? err.message : "Could not fetch video info. Please try again.";
    return NextResponse.json({ error: message }, { status: 400 });
  }
}
