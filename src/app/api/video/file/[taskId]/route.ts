import { createReadStream, existsSync } from "node:fs";
import { NextRequest, NextResponse } from "next/server";
import { downloadStore } from "@/lib/download-store";
import { Readable } from "node:stream";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function GET(
  _req: NextRequest,
  ctx: { params: Promise<{ taskId: string }> },
) {
  const { taskId } = await ctx.params;
  const task = downloadStore.get(taskId);
  if (!task || task.state !== "done" || !task.file || !existsSync(task.file)) {
    return NextResponse.json({ error: "File not ready" }, { status: 404 });
  }

  const filename = task.filename || "video.mp4";
  const stream = createReadStream(task.file);
  const webStream = Readable.toWeb(stream) as unknown as ReadableStream;

  return new NextResponse(webStream, {
    headers: {
      "Content-Type": "application/octet-stream",
      "Content-Disposition": `attachment; filename*=UTF-8''${encodeURIComponent(filename)}`,
      "Cache-Control": "no-store",
    },
  });
}
