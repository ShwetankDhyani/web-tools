"use client";

import { FormEvent, useCallback, useEffect, useState } from "react";
import { Bell, Loader2, Plus, Trash2, LogOut } from "lucide-react";
import { ToolShell } from "./tool-shell";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import type { TrackedProduct } from "@/lib/price-types";

type Me = {
  authenticated: boolean;
  username?: string;
  demo?: boolean;
};

export function PriceTrackerTool() {
  const [me, setMe] = useState<Me | null>(null);
  const [items, setItems] = useState<TrackedProduct[]>([]);
  const [username, setUsername] = useState("");
  const [code, setCode] = useState("");
  const [demoCode, setDemoCode] = useState<string | null>(null);
  const [activateUrl, setActivateUrl] = useState<string | null>(null);
  const [otpSent, setOtpSent] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [url, setUrl] = useState("");
  const [targetPrice, setTargetPrice] = useState("");
  const [name, setName] = useState("");

  const refreshMe = useCallback(async () => {
    const res = await fetch("/api/prices/auth/me");
    const data = await res.json();
    setMe(data);
    return data as Me;
  }, []);

  const refreshItems = useCallback(async () => {
    const res = await fetch("/api/prices/items");
    if (!res.ok) {
      setItems([]);
      return;
    }
    const data = await res.json();
    setItems(data.items ?? []);
  }, []);

  useEffect(() => {
    void (async () => {
      const data = await refreshMe();
      if (data.authenticated) await refreshItems();
    })();
  }, [refreshMe, refreshItems]);

  async function requestOtp(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const res = await fetch("/api/prices/auth/request-otp", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ username }),
      });
      const data = await res.json();
      if (!res.ok) {
        setError(data.error || "Could not send code.");
        setActivateUrl(data.activate_url ?? null);
        return;
      }
      setOtpSent(true);
      setDemoCode(data.code ?? null);
      setActivateUrl(data.activate_url ?? null);
    } catch {
      setError("Network error.");
    } finally {
      setBusy(false);
    }
  }

  async function verifyOtp(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const res = await fetch("/api/prices/auth/verify-otp", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ username, code }),
      });
      const data = await res.json();
      if (!res.ok) {
        setError(data.error || "Invalid code.");
        return;
      }
      await refreshMe();
      await refreshItems();
    } catch {
      setError("Network error.");
    } finally {
      setBusy(false);
    }
  }

  async function logout() {
    await fetch("/api/prices/auth/logout", { method: "POST" });
    setMe({ authenticated: false, demo: false });
    setItems([]);
    setOtpSent(false);
    setCode("");
    setDemoCode(null);
    setActivateUrl(null);
  }

  async function addItem(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const res = await fetch("/api/prices/items", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          url,
          targetPrice: Number(targetPrice),
          name: name || undefined,
        }),
      });
      const data = await res.json();
      if (!res.ok) {
        setError(data.error || "Could not add product.");
        return;
      }
      setUrl("");
      setTargetPrice("");
      setName("");
      await refreshItems();
    } catch {
      setError("Network error.");
    } finally {
      setBusy(false);
    }
  }

  async function removeItem(id: string) {
    await fetch(`/api/prices/items/${id}`, { method: "DELETE" });
    await refreshItems();
  }

  return (
    <ToolShell
      title="Price Tracker"
      description="Watch product pages and get a Telegram message when the price hits your target. Sign in with your Telegram username — no email spam."
      tag="Telegram alerts"
    >
      {!me?.authenticated ? (
        <div className="surface-panel rounded-2xl p-5 sm:p-6">
          <div className="mb-5 flex items-start gap-3">
            <span className="grid size-10 place-items-center rounded-xl bg-primary text-primary-foreground">
              <Bell className="size-5" />
            </span>
            <div>
              <h2 className="font-display text-lg font-semibold text-ink">
                Sign in with Telegram
              </h2>
              <p className="mt-1 text-sm text-muted-foreground">
                We send a one-time code to Telegram. First time: send /start to CallMeBot so
                messages can reach you.
              </p>
              {activateUrl ? (
                <a
                  href={activateUrl}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="mt-2 inline-block text-sm font-medium text-primary hover:underline"
                >
                  Open Telegram and send /start →
                </a>
              ) : (
                <a
                  href="https://t.me/CallMeBot_txtbot?text=%2Fstart"
                  target="_blank"
                  rel="noopener noreferrer"
                  className="mt-2 inline-block text-sm font-medium text-primary hover:underline"
                >
                  Open Telegram and send /start →
                </a>
              )}
            </div>
          </div>

          {!otpSent ? (
            <form onSubmit={requestOtp} className="space-y-4">
              <div className="space-y-1.5">
                <Label htmlFor="tg">Telegram username</Label>
                <Input
                  id="tg"
                  placeholder="@username"
                  value={username}
                  onChange={(e) => setUsername(e.target.value)}
                  className="h-11 rounded-xl bg-white/80"
                  required
                />
              </div>
              <Button type="submit" className="rounded-xl" disabled={busy}>
                {busy ? <Loader2 className="size-4 animate-spin" /> : null}
                Send login code
              </Button>
            </form>
          ) : (
            <form onSubmit={verifyOtp} className="space-y-4">
              {demoCode ? (
                <div className="rounded-xl border border-signal/30 bg-accent/50 px-4 py-3 text-sm">
                  <p className="font-medium text-primary">Demo code</p>
                  <p className="mt-1 font-mono text-2xl tracking-[0.2em] text-ink">{demoCode}</p>
                </div>
              ) : null}
              <div className="space-y-1.5">
                <Label htmlFor="code">Six-digit code</Label>
                <Input
                  id="code"
                  inputMode="numeric"
                  placeholder="123456"
                  value={code}
                  onChange={(e) => setCode(e.target.value)}
                  className="h-11 rounded-xl bg-white/80 font-mono tracking-widest"
                  required
                />
              </div>
              <div className="flex flex-wrap gap-2">
                <Button type="submit" className="rounded-xl" disabled={busy}>
                  {busy ? <Loader2 className="size-4 animate-spin" /> : null}
                  Verify & continue
                </Button>
                <Button
                  type="button"
                  variant="ghost"
                  className="rounded-xl"
                  onClick={() => {
                    setOtpSent(false);
                    setDemoCode(null);
                    setActivateUrl(null);
                  }}
                >
                  Back
                </Button>
              </div>
            </form>
          )}
        </div>
      ) : (
        <div className="space-y-6">
          <div className="flex flex-wrap items-center justify-between gap-3 rounded-2xl surface-panel px-5 py-4">
            <p className="text-sm">
              Signed in as{" "}
              <span className="font-semibold text-ink">@{me.username}</span>
              {me.demo ? (
                <span className="ml-2 rounded-md bg-accent px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-accent-foreground">
                  Demo
                </span>
              ) : null}
            </p>
            <Button variant="ghost" size="sm" className="rounded-lg" onClick={() => void logout()}>
              <LogOut className="size-4" />
              Sign out
            </Button>
          </div>

          <form onSubmit={addItem} className="space-y-4 rounded-2xl surface-panel p-5">
            <h2 className="font-display text-lg font-semibold text-ink">Track a product</h2>
            <div className="space-y-1.5">
              <Label htmlFor="productUrl">Product URL</Label>
              <Input
                id="productUrl"
                type="url"
                placeholder="https://www.amazon.com/dp/…"
                value={url}
                onChange={(e) => setUrl(e.target.value)}
                className="h-11 rounded-xl bg-white/80"
                required
              />
            </div>
            <div className="grid gap-4 sm:grid-cols-2">
              <div className="space-y-1.5">
                <Label htmlFor="target">Target price</Label>
                <Input
                  id="target"
                  type="number"
                  step="0.01"
                  min="0"
                  placeholder="49.99"
                  value={targetPrice}
                  onChange={(e) => setTargetPrice(e.target.value)}
                  className="h-11 rounded-xl bg-white/80"
                  required
                />
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="pname">Name (optional)</Label>
                <Input
                  id="pname"
                  placeholder="Auto-detected if blank"
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  className="h-11 rounded-xl bg-white/80"
                />
              </div>
            </div>
            <Button type="submit" className="rounded-xl" disabled={busy}>
              {busy ? <Loader2 className="size-4 animate-spin" /> : <Plus className="size-4" />}
              Add tracker
            </Button>
          </form>

          <div>
            <h2 className="mb-3 font-display text-lg font-semibold text-ink">Your trackers</h2>
            {items.length === 0 ? (
              <div className="rounded-2xl border border-dashed border-border bg-white/40 px-5 py-10 text-center text-sm text-muted-foreground">
                No products yet. Add a store URL above to start watching prices.
              </div>
            ) : (
              <ul className="space-y-3">
                {items.map((item) => (
                  <li
                    key={item.id}
                    className="flex flex-wrap items-start justify-between gap-3 rounded-2xl surface-panel px-5 py-4"
                  >
                    <div className="min-w-0 flex-1">
                      <a
                        href={item.url}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="font-medium text-ink hover:underline"
                      >
                        {item.name}
                      </a>
                      <p className="mt-1 text-sm text-muted-foreground">
                        Now{" "}
                        <span className="font-semibold text-foreground">
                          {item.currentPrice != null
                            ? `${item.currency}${item.currentPrice}`
                            : "—"}
                        </span>
                        {" · "}
                        Target {item.currency}
                        {item.targetPrice}
                      </p>
                    </div>
                    <Button
                      variant="ghost"
                      size="icon"
                      className="rounded-lg text-destructive"
                      aria-label="Remove"
                      onClick={() => void removeItem(item.id)}
                    >
                      <Trash2 className="size-4" />
                    </Button>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </div>
      )}

      {error ? (
        <div
          role="alert"
          className="mt-4 rounded-xl border border-destructive/30 bg-destructive/5 px-4 py-3 text-sm text-destructive"
        >
          {error}
        </div>
      ) : null}
    </ToolShell>
  );
}
