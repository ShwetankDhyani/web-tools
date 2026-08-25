"use client";

import { useEffect, useState } from "react";
import { Loader2, Download } from "lucide-react";
import { ToolShell } from "./tool-shell";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Progress } from "@/components/ui/progress";

type VideoInfo = {
  title: string;
  thumbnail: string;
  duration: number | null;
  qualities: number[];
  uploader?: string;
};

function fmtDuration(s: number | null) {
  if (!s) return "";
  const m = Math.floor(s / 60);
  const sec = Math.floor(s % 60);
  return `${m}:${sec.toString().padStart(2, "0")}`;
}

export function VideoDownloaderTool() {
  const [url, setUrl] = useState("");
  const [loading, setLoading] = useState(false);
  const [info, setInfo] = useState<VideoInfo | null>(null);
  const [quality, setQuality] = useState("best");
  const [progress, setProgress] = useState(0);
  const [statusText, setStatusText] = useState("");
  const [downloading, setDownloading] = useState(false);
  const [doneUrl, setDoneUrl] = useState<string | null>(null);
  const [doneName, setDoneName] = useState("");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    try {
      const params = new URLSearchParams(window.location.search);
      const shared = (params.get("url") || "").trim();
      if (shared) {
        setUrl(shared);
      }
    } catch {
      /* ignore */
    }
  }, []);

  async function fetchInfo() {
    const trimmed = url.trim();
    if (!trimmed) {
      setError("Paste a video URL first.");
      return;
    }
    setError(null);
    setInfo(null);
    setDoneUrl(null);
    setLoading(true);
    try {
      const res = await fetch("/api/video/info", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ url: trimmed }),
      });
      const data = await res.json();
      if (!res.ok) {
        setError(data.error || "Could not fetch this video.");
        return;
      }
      setInfo(data);
      setQuality("best");
    } catch {
      setError("Network error. Please try again.");
    } finally {
      setLoading(false);
    }
  }

  async function startDownload() {
    if (!url.trim() || !info) return;
    setDownloading(true);
    setDoneUrl(null);
    setError(null);
    setProgress(0);
    setStatusText("Starting download…");

    try {
      const res = await fetch("/api/video/download", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ url: url.trim(), quality }),
      });
      const data = await res.json();
      if (!res.ok) {
        setError(data.error || "Failed to start download.");
        setDownloading(false);
        return;
      }
      poll(data.task_id as string);
    } catch {
      setError("Network error.");
      setDownloading(false);
    }
  }

  function poll(taskId: string) {
    const interval = setInterval(async () => {
      try {
        const res = await fetch(`/api/video/progress/${taskId}`);
        const data = await res.json();
        if (!res.ok) {
          clearInterval(interval);
          setError(data.error || "Lost track of this download.");
          setDownloading(false);
          return;
        }
        if (data.state === "downloading") {
          setProgress(Number(data.progress) || 0);
          setStatusText(data.status_text || `${Math.round(data.progress || 0)}%`);
        } else if (data.state === "done") {
          clearInterval(interval);
          setProgress(100);
          setDoneUrl(`/api/video/file/${taskId}`);
          setDoneName(data.filename || "video.mp4");
          setDownloading(false);
        } else if (data.state === "error") {
          clearInterval(interval);
          setError(data.error || "Download failed.");
          setDownloading(false);
        }
      } catch {
        clearInterval(interval);
        setError("Lost connection to server.");
        setDownloading(false);
      }
    }, 1000);
  }

  return (
    <ToolShell
      title="Video Downloader"
      description="Paste a video link, choose quality, and save. Works with YouTube, Vimeo, X, Reddit, TikTok, and many more."
      tag="No account"
    >
      <div className="surface-panel rounded-2xl p-4 sm:p-5">
        <Label htmlFor="videoUrl" className="sr-only">
          Video URL
        </Label>
        <div className="flex flex-col gap-3 sm:flex-row">
          <Input
            id="videoUrl"
            type="url"
            inputMode="url"
            placeholder="https://youtube.com/watch?v=…"
            value={url}
            onChange={(e) => setUrl(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") void fetchInfo();
            }}
            className="h-12 flex-1 rounded-xl bg-white/80 text-base"
          />
          <Button
            size="lg"
            className="h-12 rounded-xl px-6"
            onClick={() => void fetchInfo()}
            disabled={loading}
          >
            {loading ? (
              <>
                <Loader2 className="size-4 animate-spin" />
                Fetching…
              </>
            ) : (
              "Fetch video"
            )}
          </Button>
        </div>
        <p className="mt-3 text-xs text-muted-foreground">
          Powered by yt-dlp · For personal use · Respect each site’s terms
        </p>
      </div>

      {error ? (
        <div
          role="alert"
          className="mt-4 rounded-xl border border-destructive/30 bg-destructive/5 px-4 py-3 text-sm text-destructive"
        >
          {error}
        </div>
      ) : null}

      {loading ? (
        <div className="mt-6 flex items-center gap-3 rounded-2xl surface-panel px-5 py-6 text-sm text-muted-foreground">
          <Loader2 className="size-5 animate-spin text-signal" />
          Looking up formats and metadata…
        </div>
      ) : null}

      {info ? (
        <div className="mt-6 overflow-hidden rounded-2xl surface-panel">
          <div className="grid gap-0 sm:grid-cols-[200px_1fr]">
            <div className="relative aspect-video bg-secondary sm:aspect-auto sm:min-h-[140px]">
              {info.thumbnail ? (
                // eslint-disable-next-line @next/next/no-img-element
                <img
                  src={info.thumbnail}
                  alt=""
                  className="h-full w-full object-cover"
                />
              ) : (
                <div className="grid h-full min-h-[120px] place-items-center text-muted-foreground">
                  No thumbnail
                </div>
              )}
            </div>
            <div className="flex flex-col justify-between gap-4 p-5">
              <div>
                <h2 className="font-display text-lg font-semibold leading-snug text-ink">
                  {info.title}
                </h2>
                <p className="mt-1 text-sm text-muted-foreground">
                  {[info.uploader, info.duration ? fmtDuration(info.duration) : null]
                    .filter(Boolean)
                    .join(" · ")}
                </p>
              </div>
              <div className="flex flex-col gap-3 sm:flex-row sm:items-end">
                <div className="flex-1 space-y-1.5">
                  <Label htmlFor="quality">Quality</Label>
                  <select
                    id="quality"
                    value={quality}
                    onChange={(e) => setQuality(e.target.value)}
                    className="flex h-11 w-full rounded-xl border border-input bg-white/80 px-3 text-sm outline-none focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50"
                  >
                    <option value="best">Best available</option>
                    {info.qualities.map((q) => (
                      <option key={q} value={String(q)}>
                        {q}p
                      </option>
                    ))}
                  </select>
                </div>
                <Button
                  size="lg"
                  className="h-11 rounded-xl px-5"
                  onClick={() => void startDownload()}
                  disabled={downloading}
                >
                  {downloading ? (
                    <>
                      <Loader2 className="size-4 animate-spin" />
                      Downloading…
                    </>
                  ) : (
                    <>
                      <Download className="size-4" />
                      Download
                    </>
                  )}
                </Button>
              </div>
            </div>
          </div>

          {downloading ? (
            <div className="border-t border-border/70 px-5 py-4">
              <div className="mb-2 flex justify-between text-xs text-muted-foreground">
                <span>{statusText}</span>
                <span>{Math.round(progress)}%</span>
              </div>
              <Progress value={progress} className="h-2" />
            </div>
          ) : null}

          {doneUrl ? (
            <div className="flex flex-wrap items-center justify-between gap-3 border-t border-border/70 bg-accent/40 px-5 py-4">
              <p className="text-sm font-medium text-primary">Your file is ready.</p>
              <Button
                className="rounded-xl"
                render={<a href={doneUrl} download={doneName} />}
              >
                <Download className="size-4" />
                Save to device
              </Button>
            </div>
          ) : null}
        </div>
      ) : null}
    </ToolShell>
  );
}
