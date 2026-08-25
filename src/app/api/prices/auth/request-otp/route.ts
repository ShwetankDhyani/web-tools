import { NextRequest, NextResponse } from "next/server";
import { cookies } from "next/headers";
import { createOtp, getDemoMode } from "@/lib/prices";
import { clientKey, rateLimitExceeded } from "@/lib/security";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

const CALLMEBOT_ACTIVATE = "https://t.me/CallMeBot_txtbot?text=%2Fstart";

export async function POST(req: NextRequest) {
  const ip = req.headers.get("x-forwarded-for")?.split(",")[0]?.trim() ?? "local";
  if (rateLimitExceeded(clientKey(ip, "otp"), 8, 60)) {
    return NextResponse.json({ error: "Too many requests." }, { status: 429 });
  }

  const body = await req.json().catch(() => ({}));
  const username = String(body.username ?? "")
    .trim()
    .replace(/^@/, "")
    .toLowerCase();

  if (!/^[a-zA-Z0-9_]{3,32}$/.test(username)) {
    return NextResponse.json(
      { error: "Enter a valid Telegram username (3–32 letters, numbers, underscore)." },
      { status: 400 },
    );
  }

  const { code, demo } = createOtp(username);

  // Production: wire CallMeBot with CALLMEBOT_APIKEY. Local/demo returns the code.
  const apiKey = process.env.CALLMEBOT_APIKEY;
  if (apiKey && !demo) {
    try {
      const msg = encodeURIComponent(`WebTools.wiki login code: ${code}`);
      await fetch(
        `https://api.callmebot.com/text.php?user=@${username}&text=${msg}&apikey=${apiKey}`,
      );
    } catch {
      /* fall through to demo disclosure */
    }
  }

  return NextResponse.json({
    ok: true,
    demo: demo || !apiKey,
    code: demo || !apiKey ? code : undefined,
    activate_url: CALLMEBOT_ACTIVATE,
    message:
      demo || !apiKey
        ? "Demo mode: use the code shown below. Configure CALLMEBOT_APIKEY for Telegram delivery."
        : "Check Telegram for your login code.",
  });
}

export async function GET() {
  const jar = await cookies();
  return NextResponse.json({
    demo: getDemoMode() || !process.env.CALLMEBOT_APIKEY,
    session: Boolean(jar.get("wt_session")?.value),
  });
}
