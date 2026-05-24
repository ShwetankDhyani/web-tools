import json
import os
import re
import smtplib
import sqlite3
import subprocess
import tempfile
import threading
import time
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


def _fetch_via_archive(url: str) -> str | None:
    """Try Google's webcache, then archive.org."""
    # Google cache
    try:
        cache_url = f"https://webcache.googleusercontent.com/search?q=cache:{url}"
        resp = requests.get(cache_url, headers=BROWSER_HEADERS, timeout=15)
        if resp.status_code == 200 and _has_article_content(resp.text):
            return resp.text
    except Exception:
        pass

    # archive.org
    try:
        archive_api = f"https://archive.org/wayback/available?url={url}"
        meta = requests.get(archive_api, timeout=10).json()
        snap = meta.get("archived_snapshots", {}).get("closest", {})
        if snap.get("available"):
            resp = requests.get(snap["url"], headers=BROWSER_HEADERS, timeout=15)
            if resp.status_code == 200 and _has_article_content(resp.text):
                return resp.text
    except Exception:
        pass

    return None


def _clean_article(html: str, url: str) -> dict:
    """Use readability to extract the article body."""
    from urllib.parse import urlparse

    doc = Document(html, url=url)
    title = doc.title()
    content_html = doc.summary()

    soup = BeautifulSoup(content_html, "lxml")

    # Fix relative image URLs
    parsed = urlparse(url)
    for img in soup.find_all("img"):
        src = img.get("src", "")
        if src.startswith("//"):
            img["src"] = "https:" + src
        elif src.startswith("/"):
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

    html = None

    # Strategy 1: Normal browser user-agent (works for most sites)
    html = _try_fetch(url, BROWSER_HEADERS)

    # Strategy 2: Googlebot user-agent (some sites serve full content to crawlers)
    if not html:
        html = _try_fetch(url, GOOGLEBOT_HEADERS)

    # Strategy 3: Google cache + archive.org
    if not html:
        html = _fetch_via_archive(url)

    # Strategy 4: Last resort – direct fetch without content check
    if not html:
        try:
            resp = requests.get(url, headers=BROWSER_HEADERS, timeout=15, allow_redirects=True)
            if resp.status_code == 200 and len(resp.text) > 200:
                html = resp.text
        except Exception:
            pass

    if not html:
        return jsonify({"error": "Could not fetch the article. The site may block all automated access."}), 502

    article = _clean_article(html, url)
    return jsonify(article)


# ---------------------------------------------------------------------------
# API – Price Tracker
# ---------------------------------------------------------------------------

SCRAPE_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
}


def _scrape_price(url: str) -> tuple[str | None, float | None]:
    """Scrape product name and price from a URL. Returns (name, price)."""
    try:
        resp = requests.get(url, headers=SCRAPE_HEADERS, timeout=15, allow_redirects=True)
        if resp.status_code != 200:
            return None, None

        soup = BeautifulSoup(resp.text, "lxml")
        domain = urlparse(url).netloc.lower()

        name = None
        price = None

        # Try to get product title
        og_title = soup.find("meta", property="og:title")
        if og_title and og_title.get("content"):
            name = og_title["content"].strip()
        elif soup.title:
            name = soup.title.get_text(strip=True)

        # Amazon
        if "amazon" in domain:
            price_el = (
                soup.find("span", class_="a-price-whole")
                or soup.find("span", id="priceblock_ourprice")
                or soup.find("span", id="priceblock_dealprice")
                or soup.find("span", class_="a-offscreen")
            )
            if price_el:
                price = _parse_price(price_el.get_text())
            title_el = soup.find("span", id="productTitle")
            if title_el:
                name = title_el.get_text(strip=True)

        # Flipkart
        elif "flipkart" in domain:
            price_el = soup.find("div", class_="Nx9bqj") or soup.find("div", class_="_30jeq3")
            if price_el:
                price = _parse_price(price_el.get_text())

        # Generic: look for common price patterns in JSON-LD
        if price is None:
            for script in soup.find_all("script", type="application/ld+json"):
                try:
                    ld = json.loads(script.string)
                    price = _extract_price_from_ld(ld)
                    if price is not None:
                        break
                except (json.JSONDecodeError, TypeError):
                    continue

        # Generic fallback: look for price-like patterns in meta tags
        if price is None:
            for meta in soup.find_all("meta"):
                prop = (meta.get("property") or meta.get("name") or "").lower()
                if "price" in prop and "amount" in prop:
                    val = meta.get("content", "")
                    price = _parse_price(val)
                    if price is not None:
                        break

        # Generic fallback: regex scan visible text for price patterns
        if price is None:
            text = soup.get_text()
            price_matches = re.findall(
                r'(?:[$€£₹¥])\s*([\d,]+(?:\.\d{1,2})?)|'
                r'([\d,]+(?:\.\d{1,2})?)\s*(?:USD|EUR|GBP|INR)',
                text
            )
            for m in price_matches:
                val = m[0] or m[1]
                p = _parse_price(val)
                if p and p > 0:
                    price = p
                    break

        return name, price

    except Exception:
        return None, None


def _extract_price_from_ld(data) -> float | None:
    """Recursively extract price from JSON-LD structured data."""
    if isinstance(data, dict):
        if "price" in data:
            return _parse_price(str(data["price"]))
        if "lowPrice" in data:
            return _parse_price(str(data["lowPrice"]))
        offers = data.get("offers")
        if offers:
            return _extract_price_from_ld(offers)
        for v in data.values():
            result = _extract_price_from_ld(v)
            if result is not None:
                return result
    elif isinstance(data, list):
        for item in data:
            result = _extract_price_from_ld(item)
            if result is not None:
                return result
    return None


def _parse_price(text: str) -> float | None:
    """Extract a numeric price from a text string."""
    if not text:
        return None
    cleaned = re.sub(r'[^\d.,]', '', text.strip())
    if not cleaned:
        return None
    # Handle "1,299.00" or "1.299,00" formats
    if ',' in cleaned and '.' in cleaned:
        if cleaned.rindex(',') > cleaned.rindex('.'):
            cleaned = cleaned.replace('.', '').replace(',', '.')
        else:
            cleaned = cleaned.replace(',', '')
    elif ',' in cleaned:
        parts = cleaned.split(',')
        if len(parts[-1]) == 2:
            cleaned = cleaned.replace(',', '.')
        else:
            cleaned = cleaned.replace(',', '')
    try:
        return float(cleaned)
    except ValueError:
        return None


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


def _check_prices_loop():
    """Background thread that checks prices every 30 minutes."""
    while True:
        time.sleep(1800)  # 30 minutes
        try:
            conn = _get_db()
            products = conn.execute(
                "SELECT * FROM tracked_products WHERE notified = 0"
            ).fetchall()
            conn.close()

            for product in products:
                product = dict(product)
                _, new_price = _scrape_price(product["url"])
                if new_price is None:
                    continue

                now = datetime.now(timezone.utc).isoformat()
                history = json.loads(product["price_history"] or "[]")
                history.append({"price": new_price, "date": now})
                # Keep last 100 entries
                history = history[-100:]

                conn = _get_db()
                conn.execute(
                    """UPDATE tracked_products
                       SET current_price = ?, last_checked = ?, price_history = ?
                       WHERE id = ?""",
                    (new_price, now, json.dumps(history), product["id"]),
                )

                if new_price <= product["target_price"]:
                    sent = _send_price_alert(product, new_price)
                    if sent:
                        conn.execute(
                            "UPDATE tracked_products SET notified = 1 WHERE id = ?",
                            (product["id"],),
                        )

                conn.commit()
                conn.close()

        except Exception:
            pass


# Start background price checker (only in main process, not reloader)
if not os.environ.get("WERKZEUG_RUN_MAIN") or os.environ.get("WERKZEUG_RUN_MAIN") == "true":
    _price_checker_thread = threading.Thread(target=_check_prices_loop, daemon=True)
    _price_checker_thread.start()


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
