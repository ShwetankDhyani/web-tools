import json
import os
import re
import smtplib
import sqlite3
import subprocess
import tempfile
import threading
import uuid
from datetime import datetime, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from urllib.parse import urlparse

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
# Database – Price Tracker
# ---------------------------------------------------------------------------

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "price_tracker.db")


def _get_db() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _init_db():
    conn = _get_db()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS tracked_products (
            id TEXT PRIMARY KEY,
            url TEXT NOT NULL,
            name TEXT,
            current_price REAL,
            target_price REAL NOT NULL,
            email TEXT NOT NULL,
            last_checked TEXT,
            notified INTEGER DEFAULT 0,
            created_at TEXT NOT NULL,
            price_history TEXT DEFAULT '[]'
        );

        CREATE TABLE IF NOT EXISTS email_config (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            smtp_host TEXT NOT NULL DEFAULT 'smtp.gmail.com',
            smtp_port INTEGER NOT NULL DEFAULT 587,
            smtp_user TEXT NOT NULL DEFAULT '',
            smtp_pass TEXT NOT NULL DEFAULT ''
        );
    """)
    conn.commit()
    conn.close()


_init_db()

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


@app.route("/price-tracker")
def price_tracker_page():
    return render_template("price_tracker.html")


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

BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
    "Referer": "https://www.google.com/",
    "DNT": "1",
    "Upgrade-Insecure-Requests": "1",
    "Cache-Control": "no-cache",
}

GOOGLEBOT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
}

FACEBOOK_HEADERS = {
    "User-Agent": "facebookexternalhit/1.1",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

GOOGLE_REFERRER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
    "Referer": "https://www.google.com/",
    "X-Forwarded-For": "66.249.66.1",
}


TRACKING_PARAMS = {
    "mod", "utm_source", "utm_medium", "utm_campaign", "utm_term",
    "utm_content", "ref", "fbclid", "gclid", "mc_cid", "mc_eid",
    "s_cid", "soc_src", "soc_trk", "linkId", "from", "source",
}


def _clean_url(url: str) -> str:
    """Strip tracking query parameters that break archive lookups."""
    parsed = urlparse(url)
    if not parsed.query:
        return url
    from urllib.parse import parse_qs, urlencode
    params = {k: v for k, v in parse_qs(parsed.query).items()
              if k.lower() not in TRACKING_PARAMS}
    cleaned = parsed._replace(query=urlencode(params, doseq=True))
    return cleaned.geturl()


def _has_article_content(html: str) -> bool:
    """Heuristic: check if the HTML likely has real article text."""
    soup = BeautifulSoup(html, "lxml")
    text = soup.get_text(separator=" ", strip=True)
    return len(text) > 800


def _try_fetch(url: str, headers: dict) -> str | None:
    try:
        resp = requests.get(url, headers=headers, timeout=15, allow_redirects=True)
        if resp.status_code == 200 and _has_article_content(resp.text):
            return resp.text
    except Exception:
        pass
    return None


def _fetch_via_google_cache(url: str) -> str | None:
    """Try Google's webcache."""
    try:
        cache_url = f"https://webcache.googleusercontent.com/search?q=cache:{url}"
        resp = requests.get(cache_url, headers=BROWSER_HEADERS, timeout=15)
        if resp.status_code == 200 and _has_article_content(resp.text):
            return resp.text
    except Exception:
        pass
    return None


def _clean_wayback_html(html: str) -> str:
    """Strip Wayback Machine's injected toolbar and fix archived URLs."""
    # Remove the Wayback toolbar
    html = re.sub(
        r'<!--\s*BEGIN WAYBACK TOOLBAR INSERT\s*-->.*?<!--\s*END WAYBACK TOOLBAR INSERT\s*-->',
        '', html, flags=re.DOTALL
    )
    # Remove Wayback's injected scripts/styles
    html = re.sub(r'<script[^>]*src="[^"]*web\.archive\.org[^"]*"[^>]*></script>', '', html)
    html = re.sub(r'<link[^>]*href="[^"]*web\.archive\.org[^"]*"[^>]*/?>', '', html)
    # Fix archived URLs: /web/20240101/https://... -> https://...
    html = re.sub(
        r'(?:https?://web\.archive\.org)?/web/\d+(?:im_|js_|cs_|id_)?/?(https?://)',
        r'\1', html
    )
    return html


def _fetch_via_archive_org(url: str) -> str | None:
    """Try archive.org Wayback Machine."""
    try:
        archive_api = f"https://archive.org/wayback/available?url={url}"
        meta = requests.get(archive_api, timeout=10).json()
        snap = meta.get("archived_snapshots", {}).get("closest", {})
        if snap.get("available"):
            snap_url = snap["url"]
            resp = requests.get(snap_url, headers=BROWSER_HEADERS, timeout=15)
            if resp.status_code == 200 and _has_article_content(resp.text):
                return _clean_wayback_html(resp.text)
    except Exception:
        pass
    return None


def _fetch_via_archive_today(url: str) -> str | None:
    """Try archive.today / archive.ph."""
    for domain in ("archive.ph", "archive.today", "archive.is"):
        try:
            search_url = f"https://{domain}/newest/{url}"
            resp = requests.get(
                search_url,
                headers={
                    "User-Agent": BROWSER_HEADERS["User-Agent"],
                    "Accept": "text/html,*/*",
                },
                timeout=15,
                allow_redirects=True,
            )
            if resp.status_code == 200 and _has_article_content(resp.text):
                return resp.text
        except Exception:
            continue
    return None


def _fetch_via_google_amp(url: str) -> str | None:
    """Try to find and fetch an AMP version of the page."""
    parsed = urlparse(url)
    base_path = parsed.path.rstrip("/")
    base = f"{parsed.scheme}://{parsed.netloc}"
    amp_variants = [
        f"{base}{base_path}/amp",
        f"{base}{base_path}?outputType=amp",
        f"{base}/amp{base_path}",
    ]
    for amp_url in amp_variants:
        try:
            resp = requests.get(amp_url, headers=BROWSER_HEADERS, timeout=10, allow_redirects=True)
            if resp.status_code == 200 and _has_article_content(resp.text):
                return resp.text
        except Exception:
            continue
    return None


def _resolve_url(src: str, base_url: str) -> str:
    """Resolve a potentially relative URL to absolute."""
    if src.startswith("//"):
        return "https:" + src
    if src.startswith("/"):
        return base_url + src
    if src.startswith("http"):
        return src
    return base_url + "/" + src


def _extract_site_styles(soup: BeautifulSoup, url: str) -> dict:
    """Extract style signals from the original page for theming the reader."""
    parsed = urlparse(url)
    base_url = f"{parsed.scheme}://{parsed.netloc}"

    # Collect external stylesheet URLs
    stylesheets: list[str] = []
    for link in soup.find_all("link", rel="stylesheet"):
        href = link.get("href", "")
        if href:
            stylesheets.append(_resolve_url(href, base_url))

    # Collect inline <style> blocks
    inline_styles: list[str] = []
    for style_tag in soup.find_all("style"):
        text = style_tag.get_text()
        if text and len(text) < 50000:
            inline_styles.append(text)

    # Extract favicon
    favicon = ""
    icon_link = soup.find("link", rel=lambda r: r and "icon" in r)
    if icon_link and icon_link.get("href"):
        favicon = _resolve_url(icon_link["href"], base_url)

    # Extract site name
    site_name = parsed.netloc.replace("www.", "")
    og_site = soup.find("meta", property="og:site_name")
    if og_site and og_site.get("content"):
        site_name = og_site["content"].strip()

    return {
        "stylesheets": stylesheets[:10],
        "inline_styles": inline_styles[:5],
        "favicon": favicon,
        "site_name": site_name,
        "base_url": base_url,
    }


def _extract_article_fallback(soup: BeautifulSoup) -> tuple[str, str]:
    """Fallback: extract article from <article> tag or main content area."""
    # Try <article> tag first
    article = soup.find("article")
    if article:
        text = article.get_text(strip=True)
        if len(text) > 200:
            return article.get_text(strip=True)[:80], str(article)

    # Try common content containers
    for selector in [
        '[role="main"]', "main",
        ".article-body", ".story-body", ".post-content",
        ".entry-content", ".article-content", ".article__body",
        "#article-body", "#story-body",
    ]:
        el = soup.select_one(selector)
        if el:
            text = el.get_text(strip=True)
            if len(text) > 200:
                return text[:80], str(el)

    return "", ""


def _clean_article(html: str, url: str) -> dict:
    """Extract article with readability and collect site style info."""
    full_soup = BeautifulSoup(html, "lxml")
    site_styles = _extract_site_styles(full_soup, url)

    doc = Document(html, url=url)
    title = doc.title()
    content_html = doc.summary()

    soup = BeautifulSoup(content_html, "lxml")
    article_text = soup.get_text(strip=True)

    # If readability gave us too little, try fallback extraction
    if len(article_text) < 200:
        fallback_title, fallback_html = _extract_article_fallback(full_soup)
        if fallback_html:
            content_html = fallback_html
            soup = BeautifulSoup(content_html, "lxml")
            if not title or len(title) < 5:
                title = fallback_title

    # If we still don't have a good title, try meta tags
    if not title or len(title) < 5:
        og_title = full_soup.find("meta", property="og:title")
        if og_title and og_title.get("content"):
            title = og_title["content"].strip()
        elif full_soup.title:
            title = full_soup.title.get_text(strip=True)

    parsed = urlparse(url)
    base_url = f"{parsed.scheme}://{parsed.netloc}"
    for img in soup.find_all("img"):
        src = img.get("src", "")
        img["src"] = _resolve_url(src, base_url)
        srcset = img.get("srcset", "")
        if srcset:
            parts = []
            for part in srcset.split(","):
                part = part.strip()
                parts.append(_resolve_url(part.split()[0], base_url) +
                             (" " + " ".join(part.split()[1:]) if len(part.split()) > 1 else ""))
            img["srcset"] = ", ".join(parts)

    for a_tag in soup.find_all("a"):
        href = a_tag.get("href", "")
        if href and not href.startswith(("http", "mailto:", "#", "javascript:")):
            a_tag["href"] = _resolve_url(href, base_url)
        a_tag["target"] = "_blank"

    # Remove noscript tags and JS/ad-blocker warnings
    for noscript in soup.find_all("noscript"):
        noscript.decompose()
    for el in soup.find_all(string=re.compile(
        r"(enable\s+javascript|disable.*ad\s*block|turn off.*ad\s*block"
        r"|javascript\s+is\s+(required|disabled|not\s+enabled)"
        r"|please\s+enable\s+js|browser.*not\s+support)",
        re.IGNORECASE,
    )):
        parent = el.find_parent(["div", "section", "p", "span", "aside"])
        if parent and len(parent.get_text(strip=True)) < 500:
            parent.decompose()

    # Remove script tags (they can't execute in sandbox anyway)
    for script in soup.find_all("script"):
        script.decompose()

    return {
        "title": title,
        "content": str(soup),
        "source_url": url,
        "site_styles": site_styles,
    }


def _fetch_article_html(url: str) -> str | None:
    """Try multiple strategies to fetch article HTML, from fastest to slowest."""
    clean = _clean_url(url)

    # 1. Direct fetch with browser-like headers + Google referer
    html = _try_fetch(clean, BROWSER_HEADERS)
    if html:
        return html

    # 2. Pretend to be Googlebot (many paywalls let Google through for SEO)
    html = _try_fetch(clean, GOOGLEBOT_HEADERS)
    if html:
        return html

    # 3. Facebook external hit (sites serve full OG content to Facebook)
    html = _try_fetch(clean, FACEBOOK_HEADERS)
    if html:
        return html

    # 4. Google referrer + X-Forwarded-For trick
    html = _try_fetch(clean, GOOGLE_REFERRER_HEADERS)
    if html:
        return html

    # 5. Google AMP version (many news sites have one)
    html = _fetch_via_google_amp(clean)
    if html:
        return html

    # 6. Google cache
    html = _fetch_via_google_cache(clean)
    if html:
        return html

    # 7. archive.today (often has paywalled content)
    html = _fetch_via_archive_today(clean)
    if html:
        return html

    # 8. Wayback Machine
    html = _fetch_via_archive_org(clean)
    if html:
        return html

    # 9. Last resort: accept whatever we get even if short
    try:
        resp = requests.get(clean, headers=BROWSER_HEADERS, timeout=15, allow_redirects=True)
        if resp.status_code == 200 and len(resp.text) > 200:
            return resp.text
    except Exception:
        pass

    return None


@app.route("/api/paywall/read", methods=["POST"])
def paywall_read():
    data = request.get_json(force=True)
    url = data.get("url", "").strip()
    if not url:
        return jsonify({"error": "URL is required"}), 400

    html = _fetch_article_html(url)

    if not html:
        return jsonify({"error": "Could not fetch the article. The site may block all automated access."}), 502

    article = _clean_article(html, url)
    return jsonify(article)


# ---------------------------------------------------------------------------
# API – Price Tracker
# ---------------------------------------------------------------------------

from scraper import scrape_price as _scrape_price


def _send_price_alert(product: dict, new_price: float):
    """Send an email alert about a price drop."""
    conn = _get_db()
    config = conn.execute("SELECT * FROM email_config WHERE id = 1").fetchone()
    conn.close()

    if not config or not config["smtp_user"] or not config["smtp_pass"]:
        return False

    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"Price Drop Alert: {product['name'] or 'Product'}"
    msg["From"] = config["smtp_user"]
    msg["To"] = product["email"]

    html_body = f"""
    <html>
    <body style="font-family: Arial, sans-serif; background: #0b0d11; color: #e4e6eb; padding: 20px;">
        <div style="max-width: 600px; margin: 0 auto; background: #13161d; padding: 30px; border-radius: 12px; border: 1px solid #262b36;">
            <h1 style="color: #6c5ce7; margin-top: 0;">Price Drop Alert!</h1>
            <h2 style="color: #e4e6eb;">{product['name'] or 'Your tracked product'}</h2>
            <p style="font-size: 18px;">
                Current price: <strong style="color: #00cec9; font-size: 24px;">${new_price:.2f}</strong>
            </p>
            <p style="color: #8b8f9a;">
                Your target price: ${product['target_price']:.2f}
            </p>
            <a href="{product['url']}" style="display: inline-block; margin-top: 15px; padding: 12px 24px;
                background: #6c5ce7; color: white; text-decoration: none; border-radius: 8px; font-weight: bold;">
                View Product
            </a>
            <p style="color: #8b8f9a; margin-top: 20px; font-size: 12px;">
                Sent by WebTools Price Tracker
            </p>
        </div>
    </body>
    </html>
    """
    msg.attach(MIMEText(html_body, "html"))

    try:
        with smtplib.SMTP(config["smtp_host"], config["smtp_port"]) as server:
            server.starttls()
            server.login(config["smtp_user"], config["smtp_pass"])
            server.sendmail(config["smtp_user"], product["email"], msg.as_string())
        return True
    except Exception:
        return False


# Price checking is handled by check_prices.py via cron — no background loop needed.


@app.route("/api/price/track", methods=["POST"])
def price_track():
    """Add a product to track."""
    data = request.get_json(force=True)
    url = data.get("url", "").strip()
    target_price = data.get("target_price")
    email = data.get("email", "").strip()

    if not url:
        return jsonify({"error": "Product URL is required"}), 400
    if not target_price or float(target_price) <= 0:
        return jsonify({"error": "A valid target price is required"}), 400
    if not email or "@" not in email:
        return jsonify({"error": "A valid email is required"}), 400

    target_price = float(target_price)

    # Scrape current price
    name, current_price = _scrape_price(url)

    product_id = uuid.uuid4().hex[:12]
    now = datetime.now(timezone.utc).isoformat()
    history = []
    if current_price is not None:
        history.append({"price": current_price, "date": now})

    conn = _get_db()
    conn.execute(
        """INSERT INTO tracked_products
           (id, url, name, current_price, target_price, email, last_checked, created_at, price_history)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (product_id, url, name, current_price, target_price, email, now, now, json.dumps(history)),
    )
    conn.commit()
    conn.close()

    # If already below target, send alert immediately
    if current_price is not None and current_price <= target_price:
        product = {
            "id": product_id, "url": url, "name": name,
            "current_price": current_price, "target_price": target_price,
            "email": email,
        }
        sent = _send_price_alert(product, current_price)
        if sent:
            conn = _get_db()
            conn.execute("UPDATE tracked_products SET notified = 1 WHERE id = ?", (product_id,))
            conn.commit()
            conn.close()

    return jsonify({
        "id": product_id,
        "name": name,
        "current_price": current_price,
        "target_price": target_price,
        "message": "Product is now being tracked!",
        "already_below": current_price is not None and current_price <= target_price,
    })


@app.route("/api/price/products")
def price_products():
    """List all tracked products."""
    conn = _get_db()
    rows = conn.execute(
        "SELECT * FROM tracked_products ORDER BY created_at DESC"
    ).fetchall()
    conn.close()
    products = []
    for row in rows:
        row = dict(row)
        row["price_history"] = json.loads(row["price_history"] or "[]")
        products.append(row)
    return jsonify(products)


@app.route("/api/price/delete/<product_id>", methods=["DELETE"])
def price_delete(product_id: str):
    conn = _get_db()
    conn.execute("DELETE FROM tracked_products WHERE id = ?", (product_id,))
    conn.commit()
    conn.close()
    return jsonify({"ok": True})


@app.route("/api/price/check/<product_id>", methods=["POST"])
def price_check_now(product_id: str):
    """Manually trigger a price check for a specific product."""
    conn = _get_db()
    product = conn.execute(
        "SELECT * FROM tracked_products WHERE id = ?", (product_id,)
    ).fetchone()

    if not product:
        conn.close()
        return jsonify({"error": "Product not found"}), 404

    product = dict(product)
    _, new_price = _scrape_price(product["url"])

    if new_price is None:
        conn.close()
        return jsonify({"error": "Could not fetch current price"}), 502

    now = datetime.now(timezone.utc).isoformat()
    history = json.loads(product["price_history"] or "[]")
    history.append({"price": new_price, "date": now})
    history = history[-100:]

    conn.execute(
        """UPDATE tracked_products
           SET current_price = ?, last_checked = ?, price_history = ?
           WHERE id = ?""",
        (new_price, now, json.dumps(history), product_id),
    )

    notified = False
    if new_price <= product["target_price"] and not product["notified"]:
        sent = _send_price_alert(product, new_price)
        if sent:
            conn.execute("UPDATE tracked_products SET notified = 1 WHERE id = ?", (product_id,))
            notified = True

    conn.commit()
    conn.close()

    return jsonify({
        "current_price": new_price,
        "target_price": product["target_price"],
        "below_target": new_price <= product["target_price"],
        "notified": notified,
    })


@app.route("/api/price/email-config", methods=["GET", "POST"])
def price_email_config():
    """Get or set SMTP email configuration."""
    conn = _get_db()

    if request.method == "GET":
        config = conn.execute("SELECT * FROM email_config WHERE id = 1").fetchone()
        conn.close()
        if not config:
            return jsonify({"smtp_host": "smtp.gmail.com", "smtp_port": 587, "smtp_user": "", "configured": False})
        return jsonify({
            "smtp_host": config["smtp_host"],
            "smtp_port": config["smtp_port"],
            "smtp_user": config["smtp_user"],
            "configured": bool(config["smtp_user"] and config["smtp_pass"]),
        })

    data = request.get_json(force=True)
    conn.execute("DELETE FROM email_config")
    conn.execute(
        """INSERT INTO email_config (id, smtp_host, smtp_port, smtp_user, smtp_pass)
           VALUES (1, ?, ?, ?, ?)""",
        (
            data.get("smtp_host", "smtp.gmail.com"),
            data.get("smtp_port", 587),
            data.get("smtp_user", ""),
            data.get("smtp_pass", ""),
        ),
    )
    conn.commit()
    conn.close()
    return jsonify({"ok": True, "message": "Email configuration saved."})


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)
