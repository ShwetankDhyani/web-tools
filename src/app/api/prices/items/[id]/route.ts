import { NextRequest, NextResponse } from "next/server";
import { cookies } from "next/headers";
import { deleteProduct, sessionUser, updateProduct } from "@/lib/prices";

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
  const { id } = await ctx.params;
  const ok = deleteProduct(user.username, id);
  if (!ok) {
    return NextResponse.json({ error: "Not found." }, { status: 404 });
  }
  return NextResponse.json({ ok: true });
}

export async function PATCH(
  req: NextRequest,
  ctx: { params: Promise<{ id: string }> },
) {
  const jar = await cookies();
  const user = sessionUser(jar.get("wt_session")?.value);
  if (!user) {
    return NextResponse.json({ error: "Sign in required." }, { status: 401 });
  }
  const { id } = await ctx.params;
  const body = await req.json().catch(() => ({}));
  const targetPrice = Number(body.targetPrice);
  if (!Number.isFinite(targetPrice) || targetPrice <= 0) {
    return NextResponse.json({ error: "Invalid target price." }, { status: 400 });
  }
  const item = updateProduct(user.username, id, {
    targetPrice,
    notified: false,
  });
  if (!item) {
    return NextResponse.json({ error: "Not found." }, { status: 404 });
  }
  return NextResponse.json({ item });
}
