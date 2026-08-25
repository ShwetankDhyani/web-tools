import { NextRequest, NextResponse } from "next/server";
import { nanoid } from "nanoid";
import { clientKey, rateLimitExceeded, validatePublicHttpUrl } from "@/lib/security";
import { downloadStore } from "@/lib/download-store";
import { normalizeQuality, startDownload, ytDlpAvailable } from "@/lib/yt-dlp";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function POST(req: NextRequest) {
  const ip = req.headers.get("x-forwarded-for")?.split(",")[0]?.trim() ?? "local";
  if (rateLimitExceeded(clientKey(ip, "video-dl"), 8, 60)) {
    return NextResponse.json(
      { error: "Too many downloads. Please wait a moment." },
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
  const quality = normalizeQuality(body.quality);

  if (!url) {
    return NextResponse.json({ error: "URL is required" }, { status: 400 });
  }
  const bad = await validatePublicHttpUrl(url);
  if (bad) {
    return NextResponse.json({ error: bad }, { status: 400 });
  }
  if (quality == null) {
    return NextResponse.json({ error: "Invalid quality." }, { status: 400 });
  }

  const taskId = nanoid(12);
  downloadStore.put(taskId, {
    state: "downloading",
    progress: 0,
    status_text: "Starting download…",
    error: null,
    file: null,
    filename: null,
  });

  startDownload(taskId, url, quality);
  return NextResponse.json({ task_id: taskId });
}
