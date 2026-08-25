"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { Loader2, Trash2, Shield } from "lucide-react";
import { Button } from "@/components/ui/button";
import type { PriceUser, TrackedProduct } from "@/lib/price-types";

type Overview = {
  totalProducts: number;
  active: number;
  notified: number;
  erroring: number;
  totalUsers: number;
  users: PriceUser[];
  products: TrackedProduct[];
};

export function PriceAdmin() {
  const [data, setData] = useState<Overview | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    const res = await fetch("/api/prices/admin");
    if (res.status === 401) {
      window.location.href = "/prices";
      return;
    }
    if (res.status === 403) {
      setError("You are signed in, but this account is not an admin.");
      return;
    }
    if (!res.ok) {
      setError("Could not load admin data.");
      return;
    }
    setData(await res.json());
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  async function removeProduct(id: string) {
    setBusy(true);
    await fetch(`/api/prices/admin/products/${id}`, { method: "DELETE" });
    await load();
    setBusy(false);
  }

  if (error) {
    return (
      <div className="mx-auto max-w-3xl px-4 py-14 sm:px-6">
        <p className="text-sm text-destructive">{error}</p>
        <Link href="/prices" className="mt-4 inline-block text-sm font-medium text-primary">
          ← Back to Price Tracker
        </Link>
      </div>
    );
  }

  if (!data) {
    return (
      <div className="flex items-center justify-center py-24 text-muted-foreground">
        <Loader2 className="size-5 animate-spin" />
      </div>
    );
  }

  const stats = [
    { label: "Products", value: data.totalProducts },
    { label: "Active", value: data.active },
    { label: "Alerted", value: data.notified },
    { label: "Failing", value: data.erroring },
    { label: "Users", value: data.totalUsers },
  ];

  return (
    <div className="mx-auto max-w-5xl px-4 py-10 sm:px-6">
      <div className="mb-8 flex flex-wrap items-start justify-between gap-4">
        <div>
          <p className="inline-flex items-center gap-1.5 text-xs font-semibold uppercase tracking-[0.16em] text-signal">
            <Shield className="size-3.5" />
            Admin
          </p>
          <h1 className="mt-2 font-display text-3xl font-bold text-ink">Price Tracker</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            Users, trackers, and health across the whole site.
          </p>
        </div>
        <Button variant="outline" className="rounded-xl" render={<Link href="/prices" />}>
          ← Your tracker
        </Button>
      </div>

      <div className="grid grid-cols-2 gap-3 sm:grid-cols-5">
        {stats.map((s) => (
          <div key={s.label} className="rounded-2xl surface-panel px-4 py-4">
            <p className="font-display text-2xl font-semibold text-ink">{s.value}</p>
            <p className="text-xs text-muted-foreground">{s.label}</p>
          </div>
        ))}
      </div>

      <section className="mt-10">
        <h2 className="font-display text-lg font-semibold text-ink">Users</h2>
        <div className="mt-3 overflow-x-auto rounded-2xl surface-panel">
          <table className="w-full text-left text-sm">
            <thead className="border-b border-border/70 text-xs uppercase tracking-wide text-muted-foreground">
              <tr>
                <th className="px-4 py-3 font-medium">Username</th>
                <th className="px-4 py-3 font-medium">Role</th>
                <th className="px-4 py-3 font-medium">Joined</th>
              </tr>
            </thead>
            <tbody>
              {data.users.map((u) => (
                <tr key={u.username} className="border-b border-border/50 last:border-0">
                  <td className="px-4 py-3 font-medium">@{u.username}</td>
                  <td className="px-4 py-3">
                    {u.isAdmin ? (
                      <span className="rounded-md bg-accent px-2 py-0.5 text-[10px] font-semibold uppercase text-accent-foreground">
                        Admin
                      </span>
                    ) : (
                      "Member"
                    )}
                  </td>
                  <td className="px-4 py-3 text-muted-foreground">
                    {new Date(u.createdAt).toLocaleDateString()}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <section className="mt-10">
        <h2 className="font-display text-lg font-semibold text-ink">All trackers</h2>
        {data.products.length === 0 ? (
          <p className="mt-3 rounded-2xl border border-dashed border-border px-5 py-8 text-sm text-muted-foreground">
            No products yet.
          </p>
        ) : (
          <ul className="mt-3 space-y-2">
            {data.products.map((p) => (
              <li
                key={p.id}
                className="flex flex-wrap items-start justify-between gap-3 rounded-2xl surface-panel px-4 py-3"
              >
                <div className="min-w-0 flex-1">
                  <p className="font-medium text-ink">{p.name}</p>
                  <p className="text-xs text-muted-foreground">
                    @{p.username} · now {p.currentPrice != null ? `${p.currency}${p.currentPrice}` : "—"} ·
                    target {p.currency}
                    {p.targetPrice}
                    {p.errorCount >= 3 ? " · failing" : ""}
                  </p>
                </div>
                <Button
                  variant="ghost"
                  size="icon"
                  className="text-destructive"
                  disabled={busy}
                  aria-label="Delete tracker"
                  onClick={() => void removeProduct(p.id)}
                >
                  <Trash2 className="size-4" />
                </Button>
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}
