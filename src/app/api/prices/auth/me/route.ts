import { NextResponse } from "next/server";
import { cookies } from "next/headers";
import { getDemoMode, sessionUser } from "@/lib/prices";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function GET() {
  const jar = await cookies();
  const user = sessionUser(jar.get("wt_session")?.value);
  if (!user) {
    return NextResponse.json({ authenticated: false, demo: getDemoMode() });
  }
  return NextResponse.json({
    authenticated: true,
    username: user.username,
    isAdmin: user.isAdmin,
    demo: getDemoMode(),
  });
}
