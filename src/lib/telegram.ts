const ACTIVATE_URL = "https://t.me/CallMeBot_txtbot?text=%2Fstart";

export function telegramActivateUrl() {
  return ACTIVATE_URL;
}

export async function sendTelegram(username: string, text: string): Promise<boolean> {
  const user = username.replace(/^@/, "").trim();
  if (!user) return false;
  const url = new URL("https://api.callmebot.com/text.php");
  url.searchParams.set("user", `@${user}`);
  url.searchParams.set("text", text);

  try {
    const res = await fetch(url.toString(), { method: "GET" });
    const body = (await res.text()).toLowerCase();
    if (body.includes("error") || body.includes("permission denied")) {
      return false;
    }
    return res.ok || body.includes("message queued") || body.includes("success");
  } catch {
    return false;
  }
}
