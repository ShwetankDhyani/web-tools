import { NextRequest, NextResponse } from "next/server";
import { verifyOtp } from "@/lib/prices";
import { clientKey, rateLimitExceeded } from "@/lib/security";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function POST(req: NextRequest) {
  const ip = req.headers.get("x-forwarded-for")?.split(",")[0]?.trim() ?? "local";
  if (rateLimitExceeded(clientKey(ip, "otp-verify"), 15, 60)) {
    return NextResponse.json({ error: "Too many attempts." }, { status: 429 });
  }

  const body = await req.json().catch(() => ({}));
  const username = String(body.username ?? "")
    .trim()
    .replace(/^@/, "")
    .toLowerCase();
  const code = String(body.code ?? "").trim();

  const sessionId = verifyOtp(username, code);
  if (!sessionId) {
    return NextResponse.json({ error: "Invalid or expired code." }, { status: 401 });
  }

  const res = NextResponse.json({ ok: true, username });
  res.cookies.set("wt_session", sessionId, {
    httpOnly: true,
    sameSite: "lax",
    path: "/",
    maxAge: 60 * 60 * 24 * 30,
    secure: process.env.FLASK_SESSION_SECURE === "1",
  });
  return res;
}
