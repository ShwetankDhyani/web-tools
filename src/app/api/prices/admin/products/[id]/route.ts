import { NextRequest, NextResponse } from "next/server";
import { cookies } from "next/headers";
import { deleteProductAdmin, sessionUser } from "@/lib/prices";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function DELETE(
  _req: NextRequest,
  ctx: { params: Promise<{ id: string }> },
) {
  const jar = await cookies();
  const user = sessionUser(jar.get("wt_session")?.value);
  if (!user) {
    return NextResponse.json({ error: "Sign in required." }, { status: 401 });
  }
  if (!user.isAdmin) {
    return NextResponse.json({ error: "Admin only." }, { status: 403 });
  }
  const { id } = await ctx.params;
  const ok = deleteProductAdmin(id);
  if (!ok) {
    return NextResponse.json({ error: "Not found." }, { status: 404 });
  }
  return NextResponse.json({ ok: true });
}
