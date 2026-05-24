import json
import os
import re
import subprocess
import tempfile
import threading
import uuid

import requests
from bs4 import BeautifulSoup
from flask import (
    Flask,
    Response,
    jsonify,
    render_template,
    request,
    send_file,
)
from readability import Document

app = Flask(__name__)

DOWNLOAD_DIR = os.path.join(tempfile.gettempdir(), "web_tools_downloads")
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

# In-memory store for download progress
download_tasks: dict[str, dict] = {}
task_lock = threading.Lock()

# ---------------------------------------------------------------------------
# Routes – Pages
# ---------------------------------------------------------------------------

@app.route("/")
def index():
    return render_template("index.html")


@app.route("/video-downloader")
def video_downloader_page():
    return render_template("video_downloader.html")


@app.route("/paywall-remover")
def paywall_remover_page():
    return render_template("paywall_remover.html")


# ---------------------------------------------------------------------------
# API – Video Downloader
# ---------------------------------------------------------------------------

def _run_download(task_id: str, url: str, quality: str):
    """Background worker that drives yt-dlp and updates task state."""
    try:
        fmt = "best" if quality == "best" else f"bestvideo[height<={quality}]+bestaudio/best[height<={quality}]"
        output_template = os.path.join(DOWNLOAD_DIR, f"{task_id}_%(title)s.%(ext)s")

        cmd = [
            "yt-dlp",
            "--no-playlist",
            "-f", fmt,
            "--merge-output-format", "mp4",
            "-o", output_template,
            "--newline",
            "--progress",
            url,
        ]

        proc = subprocess.Popen(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True
        )

        for line in proc.stdout:  # type: ignore[union-attr]
            line = line.strip()
            # Parse yt-dlp progress lines
            pct_match = re.search(r"(\d+(?:\.\d+)?)%", line)
            if pct_match:
                with task_lock:
                    download_tasks[task_id]["progress"] = float(pct_match.group(1))
                    download_tasks[task_id]["status_text"] = line

        proc.wait()

        if proc.returncode != 0:
            with task_lock:
                download_tasks[task_id]["state"] = "error"
                download_tasks[task_id]["error"] = "yt-dlp exited with an error. The URL may be unsupported."
            return

        # Find the downloaded file
        for fname in os.listdir(DOWNLOAD_DIR):
            if fname.startswith(task_id):
                with task_lock:
                    download_tasks[task_id]["state"] = "done"
                    download_tasks[task_id]["progress"] = 100
                    download_tasks[task_id]["file"] = os.path.join(DOWNLOAD_DIR, fname)
                    download_tasks[task_id]["filename"] = fname[len(task_id) + 1:]
                return

        with task_lock:
            download_tasks[task_id]["state"] = "error"
            download_tasks[task_id]["error"] = "Download completed but file not found."

    except Exception as exc:
        with task_lock:
            download_tasks[task_id]["state"] = "error"
            download_tasks[task_id]["error"] = str(exc)


@app.route("/api/video/info", methods=["POST"])
def video_info():
    """Return video metadata (title, thumbnail, formats) without downloading."""
    data = request.get_json(force=True)
    url = data.get("url", "").strip()
    if not url:
        return jsonify({"error": "URL is required"}), 400

    try:
        cmd = ["yt-dlp", "--dump-json", "--no-playlist", url]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if result.returncode != 0:
            return jsonify({"error": "Could not fetch video info. Check the URL."}), 400

        info = json.loads(result.stdout)
        formats_seen = set()
        quality_options = []
        for f in info.get("formats", []):
            h = f.get("height")
            if h and h not in formats_seen:
                formats_seen.add(h)
                quality_options.append(h)
        quality_options.sort(reverse=True)

        return jsonify({
            "title": info.get("title", "Unknown"),
            "thumbnail": info.get("thumbnail", ""),
            "duration": info.get("duration"),
            "qualities": quality_options,
        })
    except subprocess.TimeoutExpired:
        return jsonify({"error": "Request timed out."}), 504
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@app.route("/api/video/download", methods=["POST"])
def video_download_start():
    """Start an async download and return a task ID."""
    data = request.get_json(force=True)
    url = data.get("url", "").strip()
    quality = data.get("quality", "best")

    if not url:
        return jsonify({"error": "URL is required"}), 400

    task_id = uuid.uuid4().hex[:12]
    with task_lock:
        download_tasks[task_id] = {
            "state": "downloading",
            "progress": 0,
            "status_text": "Starting download...",
            "error": None,
            "file": None,
            "filename": None,
        }

    thread = threading.Thread(target=_run_download, args=(task_id, url, quality), daemon=True)
    thread.start()

    return jsonify({"task_id": task_id})


@app.route("/api/video/progress/<task_id>")
def video_progress(task_id: str):
    with task_lock:
        task = download_tasks.get(task_id)
    if not task:
        return jsonify({"error": "Unknown task"}), 404
    return jsonify(task)


@app.route("/api/video/file/<task_id>")
def video_file(task_id: str):
    with task_lock:
        task = download_tasks.get(task_id)
    if not task or task["state"] != "done":
        return jsonify({"error": "File not ready"}), 404

    return send_file(
        task["file"],
        as_attachment=True,
        download_name=task["filename"],
    )


# ---------------------------------------------------------------------------
# API – Paywall Remover
# ---------------------------------------------------------------------------

READER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
    "Referer": "https://www.google.com/",
    "DNT": "1",
}


def _fetch_via_archive(url: str) -> str | None:
    """Try Google's webcache, then archive.org."""
    # Google cache
    try:
        cache_url = f"https://webcache.googleusercontent.com/search?q=cache:{url}"
        resp = requests.get(cache_url, headers=READER_HEADERS, timeout=15)
        if resp.status_code == 200 and len(resp.text) > 500:
            return resp.text
    except Exception:
        pass

    # archive.org
    try:
        archive_api = f"https://archive.org/wayback/available?url={url}"
        meta = requests.get(archive_api, timeout=10).json()
        snap = meta.get("archived_snapshots", {}).get("closest", {})
        if snap.get("available"):
            resp = requests.get(snap["url"], headers=READER_HEADERS, timeout=15)
            if resp.status_code == 200:
                return resp.text
    except Exception:
        pass

    return None


def _clean_article(html: str, url: str) -> dict:
    """Use readability to extract the article body."""
    doc = Document(html, url=url)
    title = doc.title()
    content_html = doc.summary()

    # Also extract plain text for a fallback
    soup = BeautifulSoup(content_html, "lxml")

    # Fix relative image URLs
    for img in soup.find_all("img"):
        src = img.get("src", "")
        if src.startswith("//"):
            img["src"] = "https:" + src
        elif src.startswith("/"):
            from urllib.parse import urlparse

            parsed = urlparse(url)
            img["src"] = f"{parsed.scheme}://{parsed.netloc}{src}"

    return {
        "title": title,
        "content": str(soup),
        "text": soup.get_text(separator="\n", strip=True),
        "source_url": url,
    }


@app.route("/api/paywall/read", methods=["POST"])
def paywall_read():
    data = request.get_json(force=True)
    url = data.get("url", "").strip()
    if not url:
        return jsonify({"error": "URL is required"}), 400

    # Strategy 1: Direct fetch with bot-like headers (many sites serve full
    # content to crawlers for SEO).
    html = None
    try:
        resp = requests.get(url, headers=READER_HEADERS, timeout=15)
        if resp.status_code == 200:
            html = resp.text
    except Exception:
        pass

    # Strategy 2: Archive fallback
    if not html or len(html) < 500:
        archive_html = _fetch_via_archive(url)
        if archive_html:
            html = archive_html

    if not html:
        return jsonify({"error": "Could not fetch the article. The site may block all automated access."}), 502

    article = _clean_article(html, url)
    return jsonify(article)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)
