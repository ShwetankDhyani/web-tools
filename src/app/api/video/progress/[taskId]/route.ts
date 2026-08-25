import { NextRequest, NextResponse } from "next/server";
import { downloadStore, publicTaskView } from "@/lib/download-store";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function GET(
  _req: NextRequest,
  ctx: { params: Promise<{ taskId: string }> },
) {
  const { taskId } = await ctx.params;
  const task = downloadStore.get(taskId);
  if (!task) {
    return NextResponse.json({ error: "Unknown task" }, { status: 404 });
  }
  return NextResponse.json(publicTaskView(task));
}
