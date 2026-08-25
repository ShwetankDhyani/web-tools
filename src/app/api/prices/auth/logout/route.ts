import { NextResponse } from "next/server";
import { cookies } from "next/headers";
import { destroySession } from "@/lib/prices";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function POST() {
  const jar = await cookies();
  const sessionId = jar.get("wt_session")?.value;
  destroySession(sessionId);
  const res = NextResponse.json({ ok: true });
  res.cookies.set("wt_session", "", { httpOnly: true, path: "/", maxAge: 0 });
  return res;
}
