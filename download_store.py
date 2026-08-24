"""File-backed download task store — safe across Gunicorn workers."""

from __future__ import annotations

import json
import os
import threading
import time
from typing import Any

_lock = threading.Lock()


class DownloadStore:
    def __init__(self, directory: str, *, ttl_sec: int = 3600):
        self.directory = directory
        self.ttl_sec = ttl_sec
        os.makedirs(directory, exist_ok=True)

    def _path(self, task_id: str) -> str:
        safe = "".join(c for c in task_id if c.isalnum())[:32]
        return os.path.join(self.directory, f"{safe}.json")

    def put(self, task_id: str, data: dict[str, Any]) -> None:
        payload = dict(data)
        payload["_updated"] = time.time()
        path = self._path(task_id)
        tmp = path + ".tmp"
        with _lock:
            with open(tmp, "w", encoding="utf-8") as fh:
                json.dump(payload, fh)
            os.replace(tmp, path)

    def get(self, task_id: str) -> dict[str, Any] | None:
        path = self._path(task_id)
        try:
            with open(path, encoding="utf-8") as fh:
                data = json.load(fh)
        except (OSError, json.JSONDecodeError):
            return None
        updated = data.get("_updated", 0)
        if time.time() - updated > self.ttl_sec:
            self.delete(task_id)
            return None
        return data

    def update(self, task_id: str, **fields: Any) -> dict[str, Any] | None:
        with _lock:
            current = self.get(task_id) or {}
            current.update(fields)
            current["_updated"] = time.time()
            path = self._path(task_id)
            tmp = path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as fh:
                json.dump(current, fh)
            os.replace(tmp, path)
            return current

    def delete(self, task_id: str) -> None:
        path = self._path(task_id)
        try:
            os.remove(path)
        except OSError:
            pass

    def cleanup(self) -> int:
        """Remove expired task metadata and orphaned download files. Returns count removed."""
        removed = 0
        now = time.time()
        try:
            names = os.listdir(self.directory)
        except OSError:
            return 0
        for name in names:
            path = os.path.join(self.directory, name)
            try:
                age = now - os.path.getmtime(path)
            except OSError:
                continue
            if age <= self.ttl_sec:
                continue
            try:
                os.remove(path)
                removed += 1
            except OSError:
                pass
        return removed


def public_task_view(task: dict[str, Any]) -> dict[str, Any]:
    return {
        "state": task.get("state"),
        "progress": task.get("progress"),
        "status_text": task.get("status_text"),
        "error": task.get("error"),
        "filename": task.get("filename"),
    }
