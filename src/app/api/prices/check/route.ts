import { NextRequest, NextResponse } from "next/server";
import { listAllProducts, scrapeProduct, updateProduct } from "@/lib/prices";
import { sendTelegram } from "@/lib/telegram";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

/**
 * Cron: curl -H "Authorization: Bearer $CRON_SECRET" http://127.0.0.1:4321/api/prices/check
 * If CRON_SECRET is unset, only localhost is allowed.
 */
export async function POST(req: NextRequest) {
  const secret = process.env.CRON_SECRET;
  const auth = req.headers.get("authorization") ?? "";
  const ip = req.headers.get("x-forwarded-for")?.split(",")[0]?.trim();
  const local =
    !ip || ip === "127.0.0.1" || ip === "::1" || ip === "localhost";

  if (secret) {
    if (auth !== `Bearer ${secret}`) {
      return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
    }
  } else if (!local) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }

  const items = listAllProducts();
  const results: { id: string; ok: boolean; alert?: boolean }[] = [];

  for (const item of items) {
    try {
      const scraped = await scrapeProduct(item.url);
      const price = scraped.price;
      const now = new Date().toISOString();
      if (price == null) {
        updateProduct(item.username, item.id, {
          lastChecked: now,
          errorCount: item.errorCount + 1,
          lastError: "Could not read a price",
        });
        results.push({ id: item.id, ok: false });
        continue;
      }

      const history = [...item.priceHistory, { at: now, price }].slice(-40);
      let notified = item.notified;
      let alert = false;

      if (price <= item.targetPrice && !item.notified) {
        alert = await sendTelegram(
          item.username,
          `Price drop alert!\n\n${item.name}\nNow: ${item.currency}${price}\nTarget: ${item.currency}${item.targetPrice}\n\n${item.url}\n\n— WebTools.wiki`,
        );
        notified = alert;
      } else if (price > item.targetPrice && item.notified) {
        notified = false;
      }

      updateProduct(item.username, item.id, {
        currentPrice: price,
        lastChecked: now,
        priceHistory: history,
        notified,
        errorCount: 0,
        lastError: "",
      });
      results.push({ id: item.id, ok: true, alert });
    } catch {
      results.push({ id: item.id, ok: false });
    }
  }

  return NextResponse.json({ checked: results.length, results });
}
