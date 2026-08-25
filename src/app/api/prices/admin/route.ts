import { NextResponse } from "next/server";
import { cookies } from "next/headers";
import { adminOverview, listAllProducts, listUsers, sessionUser } from "@/lib/prices";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function GET() {
  const jar = await cookies();
  const user = sessionUser(jar.get("wt_session")?.value);
  if (!user) {
    return NextResponse.json({ error: "Sign in required." }, { status: 401 });
  }
  if (!user.isAdmin) {
    return NextResponse.json({ error: "Admin only." }, { status: 403 });
  }
  return NextResponse.json({
    ...adminOverview(),
    users: listUsers(),
    products: listAllProducts(),
  });
}
