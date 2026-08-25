"use client";

import { useEffect, useState } from "react";
import { Loader2 } from "lucide-react";
import { ToolShell } from "./tool-shell";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

type Article = {
  title: string;
  byline: string;
  siteName: string;
  content: string;
  wordCount: number;
  sourceUrl: string;
  favicon: string;
};

export function ReaderTool() {
  const [url, setUrl] = useState("");
  const [loading, setLoading] = useState(false);
  const [article, setArticle] = useState<Article | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    try {
      const shared = new URLSearchParams(window.location.search).get("url")?.trim();
      if (shared) setUrl(shared);
    } catch {
      /* ignore */
    }
  }, []);

  async function readArticle() {
    const trimmed = url.trim();
    if (!trimmed) {
      setError("Paste an article URL first.");
      return;
    }
    setLoading(true);
    setError(null);
    setArticle(null);
    try {
      const res = await fetch("/api/reader", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ url: trimmed }),
      });
      const data = await res.json();
      if (!res.ok) {
        setError(data.error || "Could not extract this article.");
        return;
      }
      setArticle(data);
    } catch {
      setError("Network error. Please try again.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <ToolShell
      title="Reader"
      description="Paste a news or magazine URL. We extract the article into a calm, distraction-free reading view — like a desktop reader mode, in the browser."
      tag="No account"
    >
      <div className="surface-panel rounded-2xl p-4 sm:p-5">
        <Label htmlFor="articleUrl" className="sr-only">
          Article URL
        </Label>
        <div className="flex flex-col gap-3 sm:flex-row">
          <Input
            id="articleUrl"
            type="url"
            placeholder="https://example.com/article…"
            value={url}
            onChange={(e) => setUrl(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") void readArticle();
            }}
            className="h-12 flex-1 rounded-xl bg-white/80 text-base"
          />
          <Button
            size="lg"
            className="h-12 rounded-xl px-6"
            onClick={() => void readArticle()}
            disabled={loading}
          >
            {loading ? (
              <>
                <Loader2 className="size-4 animate-spin" />
                Reading…
              </>
            ) : (
              "Read article"
            )}
          </Button>
        </div>
      </div>

      {loading ? (
        <div className="mt-6 flex items-center gap-3 rounded-2xl surface-panel px-5 py-6 text-sm text-muted-foreground">
          <Loader2 className="size-5 animate-spin text-signal" />
          Fetching and extracting readable content…
        </div>
      ) : null}

      {error ? (
        <div
          role="alert"
          className="mt-4 rounded-xl border border-destructive/30 bg-destructive/5 px-4 py-3 text-sm text-destructive"
        >
          <p>{error}</p>
          <p className="mt-1 text-xs text-destructive/80">
            Some publishers block automated access. Reader works best on publicly available HTML.
          </p>
        </div>
      ) : null}

      {article ? (
        <article className="mt-8 overflow-hidden rounded-2xl surface-panel">
          <div className="flex flex-wrap items-center justify-between gap-3 border-b border-border/70 px-5 py-3 sm:px-8">
            <div className="flex items-center gap-2 text-sm text-muted-foreground">
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img src={article.favicon} alt="" width={16} height={16} className="rounded-sm" />
              <span>{article.siteName}</span>
            </div>
            <a
              href={article.sourceUrl}
              target="_blank"
              rel="noopener noreferrer"
              className="text-sm font-medium text-primary hover:underline"
            >
              Original page →
            </a>
          </div>
          <div className="px-5 py-8 sm:px-10 sm:py-10">
            <h1 className="font-display text-3xl font-bold leading-tight tracking-tight text-ink text-balance sm:text-4xl">
              {article.title}
            </h1>
            {article.byline ? (
              <p className="mt-3 text-sm text-muted-foreground">{article.byline}</p>
            ) : null}
            <div
              className="reader-prose mt-8"
              dangerouslySetInnerHTML={{ __html: article.content }}
            />
            <div className="mt-10 flex flex-wrap items-center justify-between gap-3 border-t border-border/70 pt-4 text-sm text-muted-foreground">
              <span>{article.wordCount.toLocaleString()} words</span>
              <a
                href={article.sourceUrl}
                target="_blank"
                rel="noopener noreferrer"
                className="font-medium text-primary hover:underline"
              >
                View original →
              </a>
            </div>
          </div>
        </article>
      ) : null}
    </ToolShell>
  );
}
