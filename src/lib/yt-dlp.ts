import { spawn, spawnSync } from "node:child_process";
import { existsSync, readdirSync } from "node:fs";
import { join } from "node:path";
import { homedir } from "node:os";
import { downloadStore } from "./download-store";

function resolveYtDlp(): string[] {
  const candidates = [
    "yt-dlp",
    join(homedir(), ".local/bin/yt-dlp"),
    "/usr/local/bin/yt-dlp",
    "/usr/bin/yt-dlp",
  ];
  for (const bin of candidates) {
    if (bin === "yt-dlp") {
      const which = spawnSync(/*turbopackIgnore: true*/ "which", ["yt-dlp"], {
        encoding: "utf8",
      });
      if (which.status === 0 && which.stdout.trim()) {
        return [which.stdout.trim()];
      }
      continue;
    }
    if (existsSync(/*turbopackIgnore: true*/ bin)) return [bin];
  }
  return ["python3", "-m", "yt_dlp"];
}

export function ytDlpAvailable(): boolean {
  const cmd = resolveYtDlp();
  const probe = spawnSync(/*turbopackIgnore: true*/ cmd[0], [...cmd.slice(1), "--version"], {
    encoding: "utf8",
    timeout: 15000,
    env: { ...process.env, PATH: `${homedir()}/.local/bin:${process.env.PATH ?? ""}` },
  });
  return probe.status === 0;
}

export type VideoInfo = {
  title: string;
  thumbnail: string;
  duration: number | null;
  qualities: number[];
  uploader?: string;
};

export async function fetchVideoInfo(url: string): Promise<VideoInfo> {
  const base = resolveYtDlp();
  const args = [...base.slice(1), "--dump-json", "--no-playlist", url];

  return new Promise((resolve, reject) => {
    const child = spawn(/*turbopackIgnore: true*/ base[0], args, {
      env: { ...process.env, PATH: `${homedir()}/.local/bin:${process.env.PATH ?? ""}` },
    });
    let stdout = "";
    let stderr = "";
    const timer = setTimeout(() => {
      child.kill("SIGKILL");
      reject(new Error("Request timed out."));
    }, 45000);

    child.stdout.on("data", (chunk) => {
      stdout += chunk.toString();
    });
    child.stderr.on("data", (chunk) => {
      stderr += chunk.toString();
    });
    child.on("error", (err) => {
      clearTimeout(timer);
      reject(err);
    });
    child.on("close", (code) => {
      clearTimeout(timer);
      if (code !== 0) {
        const combined = `${stderr}\n${stdout}`.toLowerCase();
        if (combined.includes("sign in to confirm") || combined.includes("not a bot")) {
          reject(
            new Error(
              "This site is asking for a browser sign-in (bot check). Try another URL, or configure cookies for yt-dlp on the server.",
            ),
          );
          return;
        }
        reject(new Error("Could not fetch video info. Check the URL."));
        return;
      }
      try {
        const info = JSON.parse(stdout);
        const seen = new Set<number>();
        const qualities: number[] = [];
        for (const f of info.formats ?? []) {
          const h = f.height as number | undefined;
          if (h && !seen.has(h)) {
            seen.add(h);
            qualities.push(h);
          }
        }
        qualities.sort((a, b) => b - a);
        resolve({
          title: info.title ?? "Unknown",
          thumbnail: info.thumbnail ?? "",
          duration: typeof info.duration === "number" ? info.duration : null,
          qualities,
          uploader: info.uploader ?? info.channel ?? undefined,
        });
      } catch {
        reject(new Error(stderr || "Could not parse video info."));
      }
    });
  });
}

export function startDownload(taskId: string, url: string, quality: string) {
  const dir = downloadStore.directory;
  const fmt =
    quality === "best"
      ? "best"
      : `bestvideo[height<=${quality}]+bestaudio/best[height<=${quality}]`;
  const outputTemplate = join(dir, `${taskId}_%(title)s.%(ext)s`);
  const base = resolveYtDlp();
  const args = [
    ...base.slice(1),
    "--no-playlist",
    "-f",
    fmt,
    "--merge-output-format",
    "mp4",
    "-o",
    outputTemplate,
    "--newline",
    "--progress",
    url,
  ];

  const child = spawn(/*turbopackIgnore: true*/ base[0], args, {
    env: { ...process.env, PATH: `${homedir()}/.local/bin:${process.env.PATH ?? ""}` },
  });

  child.stdout.on("data", (chunk) => {
    const line = chunk.toString();
    const match = line.match(/(\d+(?:\.\d+)?)%/);
    if (match) {
      downloadStore.update(taskId, {
        progress: Number(match[1]),
        status_text: line.trim().slice(0, 200),
      });
    }
  });

  child.on("error", () => {
    downloadStore.update(taskId, {
      state: "error",
      error: "Video downloader is not configured on this server.",
    });
  });

  child.on("close", (code) => {
    if (code !== 0) {
      downloadStore.update(taskId, {
        state: "error",
        error: "Download failed. The URL may be unsupported.",
      });
      return;
    }
    try {
      const files = readdirSync(dir).filter(
        (f) => f.startsWith(taskId) && !f.endsWith(".json") && !f.endsWith(".tmp"),
      );
      if (files.length === 0) {
        downloadStore.update(taskId, {
          state: "error",
          error: "Download completed but file not found.",
        });
        return;
      }
      const filename = files[0].slice(taskId.length + 1);
      downloadStore.update(taskId, {
        state: "done",
        progress: 100,
        file: join(dir, files[0]),
        filename,
        status_text: "Ready",
      });
    } catch {
      downloadStore.update(taskId, {
        state: "error",
        error: "Download failed. Please try again later.",
      });
    }
  });
}

export function normalizeQuality(quality: unknown): string | null {
  if (quality === "best" || quality === undefined || quality === null || quality === "") {
    return "best";
  }
  const n = Number(quality);
  if (!Number.isFinite(n) || n < 144 || n > 4320) return null;
  return String(Math.round(n));
}
