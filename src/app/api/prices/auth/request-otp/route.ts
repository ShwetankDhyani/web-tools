import { NextRequest, NextResponse } from "next/server";
import { createOtp, getDemoMode } from "@/lib/prices";
import { clientKey, rateLimitExceeded } from "@/lib/security";
import { sendTelegram, telegramActivateUrl } from "@/lib/telegram";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

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

  if (!/^[a-zA-Z0-9_]{5,32}$/.test(username)) {
    return NextResponse.json(
      { error: "Enter a valid Telegram username (5–32 letters, numbers, underscore)." },
      { status: 400 },
    );
  }

  const { code } = createOtp(username);
  const demo = getDemoMode();

  if (demo) {
    return NextResponse.json({
      ok: true,
      demo: true,
      code,
      activate_url: telegramActivateUrl(),
      message: "Demo mode: use the code shown below.",
    });
  }

  const sent = await sendTelegram(
    username,
    `Your WebTools.wiki login code: ${code}\n\nThis code expires in 10 minutes.`,
  );

  if (!sent) {
    return NextResponse.json(
      {
        error:
          "Could not send your login code. Open Telegram, send /start to CallMeBot, then try again.",
        activate_url: telegramActivateUrl(),
      },
      { status: 400 },
    );
  }

  return NextResponse.json({
    ok: true,
    demo: false,
    message: "Login code sent to your Telegram.",
    activate_url: telegramActivateUrl(),
  });
}

export async function GET() {
  return NextResponse.json({
    demo: getDemoMode(),
  });
}
