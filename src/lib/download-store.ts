import { mkdirSync, readFileSync, renameSync, unlinkSync, writeFileSync, readdirSync, statSync } from "node:fs";
import { join } from "node:path";
import { tmpdir } from "node:os";

export type DownloadTask = {
  state: "downloading" | "done" | "error";
  progress: number;
  status_text: string;
  error: string | null;
  file: string | null;
  filename: string | null;
  _updated?: number;
};

const DEFAULT_DIR = join(tmpdir(), "webtools_downloads");
const TTL_SEC = 3600;

function ensureDir(dir: string) {
  mkdirSync(dir, { recursive: true });
}

export class DownloadStore {
  directory: string;
  ttlSec: number;

  constructor(directory = DEFAULT_DIR, ttlSec = TTL_SEC) {
    this.directory = directory;
    this.ttlSec = ttlSec;
    ensureDir(directory);
  }

  private pathFor(taskId: string) {
    const safe = taskId.replace(/[^a-zA-Z0-9]/g, "").slice(0, 32);
    return join(this.directory, `${safe}.json`);
  }

  put(taskId: string, data: DownloadTask) {
    const payload = { ...data, _updated: Date.now() / 1000 };
    const path = this.pathFor(taskId);
    const tmp = `${path}.tmp`;
    writeFileSync(tmp, JSON.stringify(payload));
    renameSync(tmp, path);
  }

  get(taskId: string): DownloadTask | null {
    const path = this.pathFor(taskId);
    try {
      const data = JSON.parse(readFileSync(path, "utf8")) as DownloadTask;
      const updated = data._updated ?? 0;
      if (Date.now() / 1000 - updated > this.ttlSec) {
        this.delete(taskId);
        return null;
      }
      return data;
    } catch {
      return null;
    }
  }

  update(taskId: string, fields: Partial<DownloadTask>) {
    const current = this.get(taskId) ?? {
      state: "downloading" as const,
      progress: 0,
      status_text: "",
      error: null,
      file: null,
      filename: null,
    };
    this.put(taskId, { ...current, ...fields });
  }

  delete(taskId: string) {
    try {
      unlinkSync(this.pathFor(taskId));
    } catch {
      /* ignore */
    }
  }

  cleanup() {
    const now = Date.now() / 1000;
    let removed = 0;
    try {
      for (const name of readdirSync(this.directory)) {
        const path = join(this.directory, name);
        try {
          if (now - statSync(path).mtimeMs / 1000 > this.ttlSec) {
            unlinkSync(path);
            removed += 1;
          }
        } catch {
          /* ignore */
        }
      }
    } catch {
      return 0;
    }
    return removed;
  }
}

export function publicTaskView(task: DownloadTask) {
  return {
    state: task.state,
    progress: task.progress,
    status_text: task.status_text,
    error: task.error,
    filename: task.filename,
  };
}

export const downloadStore = new DownloadStore();
