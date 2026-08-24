import json
import logging
import os
import random
import re
import sqlite3
import subprocess
import tempfile
import threading
import uuid
from datetime import datetime, timedelta, timezone
from functools import wraps
from urllib.parse import urlparse

import requests
import urllib.parse
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)
from flask import (
    Flask,
    Response,
    jsonify,
    redirect,
    render_template,
    request,
    send_file,
    session,
    url_for,
)
from readability import Document

from download_store import DownloadStore, public_task_view
from security_utils import (
    client_key,
    rate_limit_exceeded,
    sanitize_article_html,
    validate_public_http_url,
    validate_resolved_url,
)


def _load_dotenv(path: str) -> None:
    """Load KEY=VALUE pairs into os.environ without overriding existing vars."""
    try:
        with open(path, encoding="utf-8") as fh:
            for raw in fh:
                line = raw.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, _, value = line.partition("=")
                key = key.strip()
                value = value.strip().strip('"').strip("'")
                if key:
                    os.environ.setdefault(key, value)
    except FileNotFoundError:
        return
    except OSError as exc:
        logger.warning("Could not read %s: %s", path, exc)


_load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))

app = Flask(__name__)
_secret = os.environ.get("FLASK_SECRET_KEY")
if not _secret:
    logger.warning(
        "FLASK_SECRET_KEY is unset — using a random per-process secret. "
        "Sessions will break across workers; set FLASK_SECRET_KEY in production."
    )
    _secret = uuid.uuid4().hex
app.secret_key = _secret
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    # Enable in production: FLASK_SESSION_SECURE=1
    SESSION_COOKIE_SECURE=os.environ.get("FLASK_SESSION_SECURE", "0") == "1",
)

app.permanent_session_lifetime = timedelta(days=30)


@app.after_request
def _security_headers(response):
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    response.headers.setdefault(
        "Permissions-Policy",
        "camera=(), microphone=(), geolocation=(), payment=()",
    )
    response.headers.setdefault(
        "Content-Security-Policy",
        "default-src 'self'; "
        "img-src 'self' data: https:; "
        "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
        "font-src 'self' https://fonts.gstatic.com data:; "
        "script-src 'self' 'unsafe-inline'; "
        "connect-src 'self'; "
        "frame-ancestors 'none'; "
        "base-uri 'self'; "
        "form-action 'self'",
    )
    if request.is_secure or request.headers.get("X-Forwarded-Proto") == "https":
        response.headers.setdefault(
            "Strict-Transport-Security",
            "max-age=31536000; includeSubDomains",
        )
    return response


# CallMeBot — one-tap Telegram link (/start pre-filled for authorization)
CALLMEBOT_BOT = "CallMeBot_txtbot"
CALLMEBOT_ACTIVATE_URL = f"https://t.me/{CALLMEBOT_BOT}?text=%2Fstart"


@app.context_processor
def inject_callmebot():
    return {
        "callmebot_bot": CALLMEBOT_BOT,
        "callmebot_activate_url": CALLMEBOT_ACTIVATE_URL,
    }


def _telegram_activate_payload(extra: dict | None = None) -> dict:
    """JSON fields returned when Telegram delivery fails."""
    payload = {
        "error": "Activate Telegram first — tap the link to send /start to CallMeBot.",
        "activate_url": CALLMEBOT_ACTIVATE_URL,
    }
    if extra:
        payload.update(extra)
    return payload

DOWNLOAD_DIR = os.path.join(tempfile.gettempdir(), "web_tools_downloads")
os.makedirs(DOWNLOAD_DIR, exist_ok=True)
download_store = DownloadStore(DOWNLOAD_DIR, ttl_sec=3600)

# ---------------------------------------------------------------------------
# Database – Price Tracker
# ---------------------------------------------------------------------------

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "price_tracker.db")


def _get_db() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=30000")
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
            currency TEXT NOT NULL DEFAULT '$',
            username TEXT NOT NULL DEFAULT '',
            last_checked TEXT,
            notified INTEGER DEFAULT 0,
            created_at TEXT NOT NULL,
            price_history TEXT DEFAULT '[]',
            error_count INTEGER DEFAULT 0,
            last_error TEXT DEFAULT ''
        );

        CREATE TABLE IF NOT EXISTS users (
            username TEXT PRIMARY KEY,
            created_at TEXT NOT NULL,
            is_admin INTEGER DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS otp_codes (
            username TEXT PRIMARY KEY,
            code TEXT NOT NULL,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS check_runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            product_id TEXT NOT NULL,
            checked_at TEXT NOT NULL,
            success INTEGER NOT NULL,
            price REAL,
            error TEXT,
            source TEXT NOT NULL DEFAULT 'cron',
            FOREIGN KEY (product_id) REFERENCES tracked_products(id) ON DELETE CASCADE
        );

        CREATE INDEX IF NOT EXISTS idx_check_runs_product ON check_runs(product_id);
        CREATE INDEX IF NOT EXISTS idx_check_runs_time ON check_runs(checked_at);
    """)
    conn.execute("PRAGMA foreign_keys = ON")
    conn.commit()

    # Safe migrations: add columns that may not exist in older databases
    migrations = [
        ("tracked_products", "currency", "TEXT NOT NULL DEFAULT '$'"),
        ("tracked_products", "username", "TEXT NOT NULL DEFAULT ''"),
        ("tracked_products", "error_count", "INTEGER DEFAULT 0"),
        ("tracked_products", "last_error", "TEXT DEFAULT ''"),
        ("tracked_products", "check_interval", "INTEGER NOT NULL DEFAULT 3"),
        ("tracked_products", "check_count", "INTEGER NOT NULL DEFAULT 0"),
    ]
    for table, column, col_type in migrations:
        try:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {col_type}")
            conn.commit()
        except sqlite3.OperationalError:
            pass  # Column already exists

    _backfill_check_counts(conn)
    _fix_product_currencies(conn)
    conn.close()


def _backfill_check_counts(conn: sqlite3.Connection):
    """Estimate check_count for products checked before logging existed."""
    rows = conn.execute(
        "SELECT id, price_history, last_checked, check_count FROM tracked_products"
    ).fetchall()
    for row in rows:
        if row["check_count"] and row["check_count"] > 0:
            continue
        history = json.loads(row["price_history"] or "[]")
        estimated = len(history)
        if row["last_checked"] and estimated < 1:
            estimated = 1
        if estimated > 0:
            conn.execute(
                "UPDATE tracked_products SET check_count = ? WHERE id = ?",
                (estimated, row["id"]),
            )
    conn.commit()


def _detect_currency(url: str) -> str:
    """Detect currency symbol from URL domain."""
    from scraper import currency_from_url
    return currency_from_url(url)


def _fix_product_currencies(conn: sqlite3.Connection):
    """Correct currency for existing rows based on product URL."""
    for row in conn.execute("SELECT id, url, currency FROM tracked_products"):
        expected = _detect_currency(row["url"])
        if row["currency"] != expected:
            conn.execute(
                "UPDATE tracked_products SET currency = ? WHERE id = ?",
                (expected, row["id"]),
            )
    conn.commit()


_init_db()

# Admin username (set via env or defaults to first user who logs in)
ADMIN_USERNAME = os.environ.get("ADMIN_USERNAME", "").lower().strip()


# ---------------------------------------------------------------------------
# Auth helpers
# ---------------------------------------------------------------------------

def _get_current_user() -> str | None:
    """Return the logged-in Telegram username from session, or None."""
    return session.get("telegram_user")


def _clamp_check_interval(minutes) -> int:
    try:
        val = int(minutes)
    except (TypeError, ValueError):
        val = 3
    return max(2, min(60, val))


def _is_admin() -> bool:
    """Check if the current user is the admin."""
    user = _get_current_user()
    if not user:
        return False
    if ADMIN_USERNAME and user == ADMIN_USERNAME:
        return True
    conn = _get_db()
    row = conn.execute("SELECT is_admin FROM users WHERE username = ?", (user,)).fetchone()
    conn.close()
    return bool(row and row["is_admin"])


def login_required(f):
    """Decorator: redirect to login if not authenticated."""
    @wraps(f)
    def decorated(*args, **kwargs):
        if not _get_current_user():
            return redirect(url_for("price_tracker_login_page"))
        return f(*args, **kwargs)
    return decorated


def api_login_required(f):
    """Decorator: return 401 JSON if not authenticated."""
    @wraps(f)
    def decorated(*args, **kwargs):
        if not _get_current_user():
            return jsonify({"error": "Login required"}), 401
        return f(*args, **kwargs)
    return decorated


def api_admin_required(f):
    """Decorator: require authenticated admin user."""
    @wraps(f)
    def decorated(*args, **kwargs):
        if not _get_current_user():
            return jsonify({"error": "Login required"}), 401
        if not _is_admin():
            return jsonify({"error": "Admin access required"}), 403
        return f(*args, **kwargs)
    return decorated


def _normalize_video_quality(quality) -> str | None:
    """Allow only 'best' or a positive integer height."""
    if quality is None or quality == "" or quality == "best":
        return "best"
    try:
        height = int(quality)
    except (TypeError, ValueError):
        return None
    if height < 144 or height > 4320:
        return None
    return str(height)




def _send_otp_telegram(username: str, code: str) -> bool:
    """Send an OTP code to a user via CallMeBot Telegram."""
    text = f"Your WebTools.wiki login code: {code}\n\nThis code expires in 5 minutes."
    try:
        api_url = (
            f"https://api.callmebot.com/text.php"
            f"?user=@{urllib.parse.quote(username)}"
            f"&text={urllib.parse.quote(text)}"
        )
        resp = requests.get(api_url, timeout=15)
        body = resp.text.lower()
        if "error" in body or "permission denied" in body:
            logger.error("OTP Telegram error for @%s: %s", username, resp.text[:200])
            return False
        return True
    except Exception as e:
        logger.error("Failed to send OTP to @%s: %s", username, e)
        return False


# ---------------------------------------------------------------------------
# Routes – Pages
# ---------------------------------------------------------------------------

@app.route("/")
def index():
    return render_template("index.html")


@app.route("/robots.txt")
def robots_txt():
    body = (
        "User-agent: *\n"
        "Allow: /\n"
        "Disallow: /price-tracker/admin\n"
        "Disallow: /api/\n"
        "Sitemap: https://webtools.wiki/sitemap.xml\n"
    )
    return app.response_class(body, mimetype="text/plain")


@app.route("/sitemap.xml")
def sitemap_xml():
    urls = ["/", "/video-downloader", "/paywall-remover", "/price-tracker", "/privacy", "/terms", "/about"]
    items = "\n".join(
        f"  <url><loc>https://webtools.wiki{u}</loc></url>" for u in urls
    )
    body = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        f"{items}\n"
        "</urlset>\n"
    )
    return app.response_class(body, mimetype="application/xml")


@app.route("/privacy")
def privacy_page():
    return render_template("privacy.html")


@app.route("/terms")
def terms_page():
    return render_template("terms.html")


@app.route("/about")
def about_page():
    return render_template("about.html")


@app.route("/favicon.ico")
def favicon():
    return app.send_static_file("favicon.svg")


@app.route("/favicon.svg")
def favicon_svg():
    return app.send_static_file("favicon.svg")


@app.route("/video-downloader")
def video_downloader_page():
    return render_template("video_downloader.html")


@app.route("/paywall-remover")
def paywall_remover_page():
    return render_template("paywall_remover.html")


@app.route("/price-tracker")
@login_required
def price_tracker_page():
    return render_template("price_tracker.html")


@app.route("/price-tracker/admin")
@login_required
def price_tracker_admin_page():
    if not _is_admin():
        return render_template(
            "404.html",
            error_code=403,
            error_msg="Admin access required.",
        ), 403
    return render_template("price_tracker_admin.html")


@app.errorhandler(404)
def not_found(e):
    if request.path.startswith("/api/"):
        return jsonify({"error": "Not found"}), 404
    return render_template(
        "404.html",
        error_code=404,
        error_msg="We couldn't find that page. It may have moved or the link might be wrong.",
    ), 404


@app.errorhandler(500)
def server_error(e):
    if request.path.startswith("/api/"):
        return jsonify({"error": "Internal server error"}), 500
    return render_template(
        "404.html",
        error_code=500,
        error_msg="Something went wrong on our end. Please try again in a moment.",
    ), 500


@app.route("/price-tracker/login")
def price_tracker_login_page():
    if _get_current_user():
        return redirect(url_for("price_tracker_page"))
    return render_template("price_tracker_login.html")


# ---------------------------------------------------------------------------
# API – Auth
# ---------------------------------------------------------------------------

@app.route("/api/auth/request-otp", methods=["POST"])
def auth_request_otp():
    """Send a one-time login code via Telegram."""
    if rate_limit_exceeded(client_key(request.remote_addr, "otp-req"), limit=5, window_sec=600):
        return jsonify({"error": "Too many login attempts. Try again in a few minutes."}), 429
    data = request.get_json(force=True) or {}
    username = (data.get("username") or "").strip().lower().lstrip("@")
    if not username:
        return jsonify({"error": "Telegram username is required"}), 400
    if not re.match(r'^[a-z0-9_]{5,32}$', username):
        return jsonify({"error": "Invalid Telegram username"}), 400
    if rate_limit_exceeded(client_key(username, "otp-req-user"), limit=3, window_sec=600):
        return jsonify({"error": "Too many codes requested for this username. Try later."}), 429

    code = f"{random.randint(100000, 999999)}"
    now = datetime.now(timezone.utc).isoformat()

    conn = _get_db()
    conn.execute(
        "INSERT OR REPLACE INTO otp_codes (username, code, created_at) VALUES (?, ?, ?)",
        (username, code, now),
    )
    conn.commit()
    conn.close()

    if not _send_otp_telegram(username, code):
        return jsonify(_telegram_activate_payload({
            "error": "Could not send your login code. Tap “Open Telegram & send /start” below, then try again.",
        })), 400

    return jsonify({"ok": True, "message": "Login code sent to your Telegram."})


@app.route("/api/auth/verify-otp", methods=["POST"])
def auth_verify_otp():
    """Verify the OTP and create a session."""
    if rate_limit_exceeded(client_key(request.remote_addr, "otp-verify"), limit=12, window_sec=600):
        return jsonify({"error": "Too many attempts. Request a new code later."}), 429
    data = request.get_json(force=True) or {}
    username = (data.get("username") or "").strip().lower().lstrip("@")
    code = (data.get("code") or "").strip()

    if not username or not code:
        return jsonify({"error": "Username and code are required"}), 400
    if rate_limit_exceeded(client_key(username, "otp-verify-user"), limit=8, window_sec=600):
        return jsonify({"error": "Too many attempts for this username. Try later."}), 429

    conn = _get_db()
    row = conn.execute(
        "SELECT * FROM otp_codes WHERE username = ?", (username,)
    ).fetchone()

    if not row or row["code"] != code:
        conn.close()
        return jsonify({"error": "Invalid code. Please try again."}), 400

    # Check expiry (5 minutes)
    created = datetime.fromisoformat(row["created_at"])
    if (datetime.now(timezone.utc) - created).total_seconds() > 300:
        conn.execute("DELETE FROM otp_codes WHERE username = ?", (username,))
        conn.commit()
        conn.close()
        return jsonify({"error": "Code expired. Request a new one."}), 400

    # Delete used OTP
    conn.execute("DELETE FROM otp_codes WHERE username = ?", (username,))

    # Create or update user
    now = datetime.now(timezone.utc).isoformat()
    existing = conn.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
    if not existing:
        # First user to register becomes admin if ADMIN_USERNAME is not set
        user_count = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
        is_admin = 1 if (user_count == 0 and not ADMIN_USERNAME) else 0
        conn.execute(
            "INSERT INTO users (username, created_at, is_admin) VALUES (?, ?, ?)",
            (username, now, is_admin),
        )

    conn.commit()
    conn.close()

    session["telegram_user"] = username
    session.permanent = True
    return jsonify({"ok": True, "username": username})


@app.route("/api/auth/logout", methods=["POST"])
def auth_logout():
    session.pop("telegram_user", None)
    return jsonify({"ok": True})


@app.route("/api/auth/me")
def auth_me():
    """Return current user info."""
    user = _get_current_user()
    if not user:
        return jsonify({"logged_in": False})
    return jsonify({
        "logged_in": True,
        "username": user,
        "is_admin": _is_admin(),
    })


# ---------------------------------------------------------------------------
# API – Video Downloader
# ---------------------------------------------------------------------------

def _yt_dlp_cmd(*args: str) -> list[str]:
    """Prefer PATH binary; fall back to python -m yt_dlp."""
    import shutil
    import sys

    if shutil.which("yt-dlp"):
        return ["yt-dlp", *args]
    return [sys.executable, "-m", "yt_dlp", *args]


def _run_download(task_id: str, url: str, quality: str):
    """Background worker that drives yt-dlp and updates task state."""
    try:
        fmt = "best" if quality == "best" else f"bestvideo[height<={quality}]+bestaudio/best[height<={quality}]"
        output_template = os.path.join(DOWNLOAD_DIR, f"{task_id}_%(title)s.%(ext)s")

        cmd = _yt_dlp_cmd(
            "--no-playlist",
            "-f", fmt,
            "--merge-output-format", "mp4",
            "-o", output_template,
            "--newline",
            "--progress",
            url,
        )

        proc = subprocess.Popen(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True
        )

        for line in proc.stdout:  # type: ignore[union-attr]
            line = line.strip()
            pct_match = re.search(r"(\d+(?:\.\d+)?)%", line)
            if pct_match:
                download_store.update(
                    task_id,
                    progress=float(pct_match.group(1)),
                    status_text=line[:200],
                )

        proc.wait()

        if proc.returncode != 0:
            download_store.update(
                task_id,
                state="error",
                error="Download failed. The URL may be unsupported.",
            )
            return

        for fname in os.listdir(DOWNLOAD_DIR):
            if fname.startswith(task_id) and not fname.endswith(".json"):
                download_store.update(
                    task_id,
                    state="done",
                    progress=100,
                    file=os.path.join(DOWNLOAD_DIR, fname),
                    filename=fname[len(task_id) + 1 :],
                )
                return

        download_store.update(
            task_id,
            state="error",
            error="Download completed but file not found.",
        )

    except FileNotFoundError:
        download_store.update(
            task_id,
            state="error",
            error="Video downloader is not configured on this server.",
        )
    except Exception:
        logger.exception("Video download failed for task %s", task_id)
        download_store.update(
            task_id,
            state="error",
            error="Download failed. Please try again later.",
        )


@app.route("/api/video/info", methods=["POST"])
def video_info():
    """Return video metadata (title, thumbnail, formats) without downloading."""
    if rate_limit_exceeded(client_key(request.remote_addr, "video-info"), limit=20, window_sec=60):
        return jsonify({"error": "Too many requests. Please wait a moment."}), 429
    data = request.get_json(force=True) or {}
    url = (data.get("url") or "").strip()
    if not url:
        return jsonify({"error": "URL is required"}), 400
    bad = validate_public_http_url(url)
    if bad:
        return jsonify({"error": bad}), 400

    try:
        download_store.cleanup()
        cmd = _yt_dlp_cmd("--dump-json", "--no-playlist", url)
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=45)
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
    except FileNotFoundError:
        return jsonify({"error": "Video downloader is not configured on this server."}), 503
    except subprocess.TimeoutExpired:
        return jsonify({"error": "Request timed out."}), 504
    except Exception:
        logger.exception("video_info failed")
        return jsonify({"error": "Could not fetch video info. Please try again."}), 500


@app.route("/api/video/download", methods=["POST"])
def video_download_start():
    """Start an async download and return a task ID."""
    if rate_limit_exceeded(client_key(request.remote_addr, "video-dl"), limit=8, window_sec=60):
        return jsonify({"error": "Too many downloads. Please wait a moment."}), 429
    data = request.get_json(force=True) or {}
    url = (data.get("url") or "").strip()
    quality = _normalize_video_quality(data.get("quality", "best"))

    if not url:
        return jsonify({"error": "URL is required"}), 400
    bad = validate_public_http_url(url)
    if bad:
        return jsonify({"error": bad}), 400
    if quality is None:
        return jsonify({"error": "Invalid quality."}), 400

    task_id = uuid.uuid4().hex[:12]
    download_store.put(task_id, {
        "state": "downloading",
        "progress": 0,
        "status_text": "Starting download...",
        "error": None,
        "file": None,
        "filename": None,
    })

    thread = threading.Thread(target=_run_download, args=(task_id, url, quality), daemon=True)
    thread.start()

    return jsonify({"task_id": task_id})


@app.route("/api/video/progress/<task_id>")
def video_progress(task_id: str):
    task = download_store.get(task_id)
    if not task:
        return jsonify({"error": "Unknown task"}), 404
    return jsonify(public_task_view(task))


@app.route("/api/video/file/<task_id>")
def video_file(task_id: str):
    task = download_store.get(task_id)
    if not task or task.get("state") != "done" or not task.get("file"):
        return jsonify({"error": "File not ready"}), 404
    if not os.path.isfile(task["file"]):
        return jsonify({"error": "File not ready"}), 404

    return send_file(
        task["file"],
        as_attachment=True,
        download_name=task.get("filename") or "video.mp4",
    )


# ---------------------------------------------------------------------------
# API – Paywall Remover
# ---------------------------------------------------------------------------

from curl_cffi import requests as cffi_requests

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


def _has_article_content(html: str, min_chars: int = 500) -> bool:
    """Heuristic: check if the HTML likely has real article text."""
    soup = BeautifulSoup(html, "lxml")
    text = soup.get_text(separator=" ", strip=True)
    if len(text) < min_chars:
        return False
    # Reject "enable JavaScript" / captcha pages
    lower = text.lower()
    blockers = ["enable javascript", "just a moment", "checking your browser",
                "complete the security check", "please verify"]
    for b in blockers:
        if b in lower and len(text) < 2000:
            return False
    return True


def _try_fetch(url: str, headers: dict) -> str | None:
    try:
        resp = cffi_requests.get(url, headers=headers, timeout=15,
                                 allow_redirects=True, impersonate="chrome")
        final = str(getattr(resp, "url", url) or url)
        if not validate_resolved_url(final):
            logger.warning("Blocked redirect to unsafe host: %s", final[:120])
            return None
        if resp.status_code == 200 and _has_article_content(resp.text):
            return resp.text
    except Exception:
        pass
    return None


def _fetch_via_google_cache(url: str) -> str | None:
    """Try Google's webcache."""
    try:
        cache_url = f"https://webcache.googleusercontent.com/search?q=cache:{url}"
        resp = cffi_requests.get(cache_url, impersonate="chrome", timeout=15)
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
        meta = cffi_requests.get(archive_api, impersonate="chrome", timeout=10).json()
        snap = meta.get("archived_snapshots", {}).get("closest", {})
        if snap.get("available"):
            snap_url = snap["url"]
            resp = cffi_requests.get(snap_url, impersonate="chrome", timeout=15)
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
            resp = cffi_requests.get(
                search_url,
                impersonate="chrome",
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
            resp = cffi_requests.get(amp_url, impersonate="chrome",
                                     timeout=10, allow_redirects=True)
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
    """Extract article with readability, return clean reader-mode HTML."""
    full_soup = BeautifulSoup(html, "lxml")

    # Extract metadata
    og_image = ""
    og_img_tag = full_soup.find("meta", property="og:image")
    if og_img_tag and og_img_tag.get("content"):
        og_image = og_img_tag["content"]

    og_desc = ""
    og_desc_tag = full_soup.find("meta", property="og:description")
    if og_desc_tag and og_desc_tag.get("content"):
        og_desc = og_desc_tag["content"]

    author = ""
    author_tag = full_soup.find("meta", attrs={"name": "author"})
    if author_tag and author_tag.get("content"):
        author = author_tag["content"]

    published = ""
    for attr in ["article:published_time", "datePublished", "date"]:
        pub_tag = full_soup.find("meta", property=attr) or full_soup.find("meta", attrs={"name": attr})
        if pub_tag and pub_tag.get("content"):
            published = pub_tag["content"][:10]
            break

    # Extract with readability
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
                tokens = part.split()
                parts.append(_resolve_url(tokens[0], base_url) +
                             (" " + " ".join(tokens[1:]) if len(tokens) > 1 else ""))
            img["srcset"] = ", ".join(parts)

    for a_tag in soup.find_all("a"):
        href = a_tag.get("href", "")
        if href and not href.startswith(("http", "mailto:", "#", "javascript:")):
            a_tag["href"] = _resolve_url(href, base_url)
        a_tag["target"] = "_blank"

    # Remove noscript tags, scripts, and JS/ad-blocker warnings
    for tag in soup.find_all(["noscript", "script", "style"]):
        tag.decompose()
    for el in soup.find_all(string=re.compile(
        r"(enable\s+javascript|disable.*ad\s*block|turn off.*ad\s*block"
        r"|javascript\s+is\s+(required|disabled|not\s+enabled)"
        r"|please\s+enable\s+js|browser.*not\s+support)",
        re.IGNORECASE,
    )):
        parent = el.find_parent(["div", "section", "p", "span", "aside"])
        if parent and len(parent.get_text(strip=True)) < 500:
            parent.decompose()

    # Remove hidden elements and paywall overlays
    for el in soup.find_all(attrs={"style": re.compile(r"display\s*:\s*none", re.I)}):
        el.decompose()

    # Get word count
    final_text = soup.get_text(strip=True)
    word_count = len(final_text.split())

    site_name = parsed.netloc.replace("www.", "")
    favicon = f"{parsed.scheme}://{parsed.netloc}/favicon.ico"

    return {
        "title": title,
        "content": str(soup),
        "source_url": url,
        "site_name": site_name,
        "favicon": favicon,
        "author": author,
        "published": published,
        "description": og_desc,
        "og_image": og_image,
        "word_count": word_count,
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
        resp = cffi_requests.get(clean, impersonate="chrome", timeout=15,
                                 allow_redirects=True)
        if resp.status_code == 200 and len(resp.text) > 200:
            return resp.text
    except Exception:
        pass

    return None


@app.route("/api/paywall/read", methods=["POST"])
def paywall_read():
    if rate_limit_exceeded(client_key(request.remote_addr, "paywall"), limit=15, window_sec=60):
        return jsonify({"error": "Too many requests. Please wait a moment."}), 429
    data = request.get_json(force=True) or {}
    url = (data.get("url") or "").strip()
    if not url:
        return jsonify({"error": "URL is required"}), 400
    bad = validate_public_http_url(url)
    if bad:
        return jsonify({"error": bad}), 400

    html = _fetch_article_html(url)

    if not html:
        return jsonify({"error": "Could not fetch the article. The site may block all automated access."}), 502

    article = _clean_article(html, url)
    article["content"] = sanitize_article_html(article.get("content") or "")
    return jsonify(article)


# ---------------------------------------------------------------------------
# API – Price Tracker
# ---------------------------------------------------------------------------

from price_log import record_price_check
from scraper import prepare_product_url, scrape_price as _scrape_price


def _shorten_url(url: str) -> str:
    """Shorten a product URL for messaging (keep domain + short path)."""
    try:
        parsed = urlparse(url)
        path = parsed.path
        if len(path) > 60:
            path = path[:57] + "..."
        return f"{parsed.scheme}://{parsed.hostname}{path}"
    except Exception:
        return url[:100] if len(url) > 100 else url


def _send_telegram_alert(product: dict, new_price: float):
    """Send a Telegram alert to the product's owner via CallMeBot."""
    username = product.get("username", "")
    if not username:
        logger.info("No username on product — skipping alert")
        return False

    cur = product.get("currency", "$")
    short_url = _shorten_url(product['url'])
    text = (
        f"Price Drop Alert!\n\n"
        f"{product['name'] or 'Product'}\n"
        f"Current price: {cur}{new_price:,.2f}\n"
        f"Your target: {cur}{product['target_price']:,.2f}\n\n"
        f"{short_url}\n\n"
        f"- WebTools.wiki Price Tracker"
    )

    try:
        api_url = (
            f"https://api.callmebot.com/text.php"
            f"?user=@{urllib.parse.quote(username)}"
            f"&text={urllib.parse.quote(text)}"
        )
        logger.info("Sending Telegram alert to @%s", username)
        resp = requests.get(api_url, timeout=15)
        body = resp.text.lower()
        if "error" in body or "permission denied" in body:
            logger.error("Telegram API error: %s", resp.text[:200])
            return False
        logger.info("Telegram alert sent successfully")
        return True
    except Exception as e:
        logger.error("Failed to send Telegram alert: %s", e)
        return False


# Price checking is handled by check_prices.py via cron — no background loop needed.


@app.route("/api/price/track", methods=["POST"])
@api_login_required
def price_track():
    """Add a product to track."""
    user = _get_current_user()
    data = request.get_json(force=True)
    url = prepare_product_url(data.get("url", ""))
    target_price = data.get("target_price")

    if not url:
        return jsonify({"error": "Product URL is required"}), 400
    if not url.startswith(("http://", "https://")):
        return jsonify({"error": "Paste a valid product link (https://…)"}), 400
    bad_url = validate_public_http_url(url)
    if bad_url:
        return jsonify({"error": bad_url}), 400
    if not target_price or float(target_price) <= 0:
        return jsonify({"error": "A valid target price is required"}), 400

    target_price = float(target_price)
    check_interval = _clamp_check_interval(data.get("check_interval", 3))

    # Scrape current price (resolves short links like amzn.in → amazon.in/dp/…)
    name, current_price, currency, resolved_url = _scrape_price(url)
    url = resolved_url or url
    if not currency:
        currency = _detect_currency(url)

    product_id = uuid.uuid4().hex[:12]
    now = datetime.now(timezone.utc).isoformat()
    history = []
    if current_price is not None:
        history.append({"price": current_price, "date": now})

    conn = _get_db()
    conn.execute(
        """INSERT INTO tracked_products
           (id, url, name, current_price, target_price, currency, username,
            last_checked, created_at, price_history, check_interval)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            product_id, url, name, current_price, target_price, currency, user,
            now, now, json.dumps(history), check_interval,
        ),
    )
    record_price_check(
        product_id,
        current_price is not None,
        price=current_price,
        error=None if current_price is not None else "Could not fetch price on add",
        source="initial",
        conn=conn,
    )
    conn.commit()
    conn.close()

    # If already below target, send alert immediately
    if current_price is not None and current_price <= target_price:
        product = {
            "id": product_id, "url": url, "name": name,
            "current_price": current_price, "target_price": target_price,
            "username": user, "currency": currency,
        }
        if _send_telegram_alert(product, current_price):
            conn = _get_db()
            conn.execute("UPDATE tracked_products SET notified = 1 WHERE id = ?", (product_id,))
            conn.commit()
            conn.close()

    return jsonify({
        "id": product_id,
        "name": name,
        "url": url,
        "current_price": current_price,
        "target_price": target_price,
        "currency": currency,
        "check_interval": check_interval,
        "message": "Product is now being tracked!",
        "already_below": current_price is not None and current_price <= target_price,
    })


@app.route("/api/price/update/<product_id>", methods=["PATCH"])
@api_login_required
def price_update(product_id: str):
    """Update check interval for a tracked product."""
    user = _get_current_user()
    conn = _get_db()
    product = conn.execute(
        "SELECT * FROM tracked_products WHERE id = ?", (product_id,)
    ).fetchone()
    if not product:
        conn.close()
        return jsonify({"error": "Product not found"}), 404
    product = dict(product)
    if not _is_admin() and not _user_owns_product(product, user):
        conn.close()
        return jsonify({"error": "Not allowed"}), 403

    data = request.get_json(force=True)
    if "check_interval" not in data:
        conn.close()
        return jsonify({"error": "Nothing to update"}), 400

    interval = _clamp_check_interval(data["check_interval"])
    conn.execute(
        "UPDATE tracked_products SET check_interval = ? WHERE id = ?",
        (interval, product_id),
    )
    conn.commit()
    conn.close()
    return jsonify({"ok": True, "check_interval": interval})


@app.route("/api/price/products")
@api_login_required
def price_products():
    """List tracked products for the current user."""
    user = _get_current_user()
    conn = _get_db()
    rows = conn.execute(
        "SELECT * FROM tracked_products WHERE username = ? ORDER BY created_at DESC",
        (user,),
    ).fetchall()
    conn.close()
    products = []
    for row in rows:
        row = dict(row)
        row["price_history"] = json.loads(row["price_history"] or "[]")
        products.append(row)
    return jsonify(products)


def _user_owns_product(product: dict, user: str) -> bool:
    """True if product belongs to user (case-insensitive username match)."""
    owner = (product.get("username") or "").strip().lower()
    return owner == (user or "").strip().lower()


@app.route("/api/price/delete/<product_id>", methods=["DELETE"])
@api_login_required
def price_delete(product_id: str):
    user = _get_current_user()
    conn = _get_db()
    product = conn.execute(
        "SELECT id, username FROM tracked_products WHERE id = ?", (product_id,)
    ).fetchone()
    if not product:
        conn.close()
        return jsonify({"error": "Product not found"}), 404
    product = dict(product)
    if not _is_admin() and not _user_owns_product(product, user):
        conn.close()
        return jsonify({"error": "Not allowed"}), 403

    conn.execute("DELETE FROM check_runs WHERE product_id = ?", (product_id,))
    conn.execute("DELETE FROM tracked_products WHERE id = ?", (product_id,))
    deleted = conn.total_changes
    conn.commit()
    conn.close()
    if deleted < 1:
        return jsonify({"error": "Product not found"}), 404
    return jsonify({"ok": True})


@app.route("/api/price/check/<product_id>", methods=["POST"])
@api_login_required
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
    user = _get_current_user()
    if not _is_admin() and not _user_owns_product(product, user):
        conn.close()
        return jsonify({"error": "Not allowed"}), 403

    _, new_price, scraped_currency, resolved_url = _scrape_price(product["url"])
    now = datetime.now(timezone.utc).isoformat()

    if new_price is None:
        error_count = product.get("error_count", 0) + 1
        conn.execute(
            """UPDATE tracked_products
               SET error_count = ?, last_error = ?, last_checked = ?
               WHERE id = ?""",
            (error_count, f"Manual check failed at {now}", now, product_id),
        )
        record_price_check(
            product_id, False, error="Could not fetch current price", source="manual", conn=conn
        )
        conn.commit()
        conn.close()
        return jsonify({"error": "Could not fetch current price"}), 502

    history = json.loads(product["price_history"] or "[]")
    history.append({"price": new_price, "date": now})
    history = history[-100:]

    store_url = resolved_url or product["url"]
    currency = scraped_currency or product.get("currency") or _detect_currency(store_url)
    conn.execute(
        """UPDATE tracked_products
           SET current_price = ?, last_checked = ?, price_history = ?,
               error_count = 0, last_error = '', currency = ?, url = ?
           WHERE id = ?""",
        (new_price, now, json.dumps(history), currency, store_url, product_id),
    )
    record_price_check(product_id, True, price=new_price, source="manual", conn=conn)
    product["currency"] = currency

    notified = False
    if new_price <= product["target_price"]:
        if not product["notified"]:
            if _send_telegram_alert(product, new_price):
                conn.execute("UPDATE tracked_products SET notified = 1 WHERE id = ?", (product_id,))
                notified = True
    else:
        if product["notified"]:
            conn.execute("UPDATE tracked_products SET notified = 0 WHERE id = ?", (product_id,))

    conn.commit()
    conn.close()

    return jsonify({
        "current_price": new_price,
        "target_price": product["target_price"],
        "currency": currency,
        "below_target": new_price <= product["target_price"],
        "notified": notified,
    })


@app.route("/api/price/test-notification", methods=["POST"])
@api_login_required
def test_notification():
    """Send a test Telegram notification to verify the user's account works."""
    user = _get_current_user()
    test_product = {
        "name": "Test Product",
        "url": "https://example.com/product",
        "target_price": 50.00,
        "username": user,
        "currency": "$",
    }
    result = _send_telegram_alert(test_product, 42.99)
    if result:
        return jsonify({"ok": True})
    return jsonify(_telegram_activate_payload({
        "ok": False,
        "error": "Test message failed. Activate Telegram first.",
    }))


# ---------------------------------------------------------------------------
# API – Price Tracker Admin
# ---------------------------------------------------------------------------

@app.route("/api/price/status")
@api_admin_required
def price_tracker_status():
    """Overview of tracker health (admin only)."""
    conn = _get_db()
    total = conn.execute("SELECT COUNT(*) FROM tracked_products").fetchone()[0]
    notified = conn.execute("SELECT COUNT(*) FROM tracked_products WHERE notified = 1").fetchone()[0]
    active = total - notified
    erroring = conn.execute("SELECT COUNT(*) FROM tracked_products WHERE error_count >= 3").fetchone()[0]
    user_count = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    last_checked_row = conn.execute(
        "SELECT last_checked FROM tracked_products ORDER BY last_checked DESC LIMIT 1"
    ).fetchone()
    try:
        check_stats = conn.execute(
            """SELECT
                 COUNT(*) AS total,
                 COALESCE(SUM(success), 0) AS successful,
                 COALESCE(SUM(CASE WHEN success = 0 THEN 1 ELSE 0 END), 0) AS failed
               FROM check_runs"""
        ).fetchone()
    except sqlite3.OperationalError:
        check_stats = {"total": 0, "successful": 0, "failed": 0}
    conn.close()

    return jsonify({
        "total_products": total,
        "active": active,
        "notified": notified,
        "erroring": erroring,
        "total_users": user_count,
        "last_checked": last_checked_row["last_checked"] if last_checked_row else None,
        "check_runs": {
            "total": check_stats["total"] or 0,
            "successful": check_stats["successful"] or 0,
            "failed": check_stats["failed"] or 0,
        },
    })


@app.route("/api/price/admin/products")
@api_admin_required
def admin_products():
    """List all products with error info for admin view."""
    conn = _get_db()
    rows = conn.execute(
        """SELECT p.*,
                  COALESCE(p.check_count, 0) AS check_total,
                  (SELECT COUNT(*) FROM check_runs c WHERE c.product_id = p.id AND c.success = 1) AS check_success,
                  (SELECT COUNT(*) FROM check_runs c WHERE c.product_id = p.id AND c.success = 0) AS check_failed
           FROM tracked_products p
           ORDER BY p.error_count DESC, p.created_at DESC"""
    ).fetchall()
    conn.close()
    products = []
    for row in rows:
        r = dict(row)
        r["price_history"] = json.loads(r["price_history"] or "[]")
        products.append(r)
    return jsonify(products)


@app.route("/api/price/admin/check-history")
@api_admin_required
def admin_check_history():
    """Recent check iterations across all products (admin only)."""
    limit = min(int(request.args.get("limit", 40)), 100)
    conn = _get_db()
    rows = conn.execute(
        """SELECT c.id, c.product_id, c.checked_at, c.success, c.price, c.error, c.source,
                  p.name, p.url, p.username, p.currency
           FROM check_runs c
           JOIN tracked_products p ON p.id = c.product_id
           ORDER BY c.checked_at DESC
           LIMIT ?""",
        (limit,),
    ).fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])


@app.route("/api/price/admin/cleanup", methods=["POST"])
@api_admin_required
def admin_cleanup():
    """Remove notified products older than N days."""
    data = request.get_json(force=True)
    days = int(data.get("days", 7))
    conn = _get_db()
    cutoff = datetime.now(timezone.utc).isoformat()
    result = conn.execute(
        """DELETE FROM tracked_products
           WHERE notified = 1
           AND created_at < datetime(?, '-' || ? || ' days')""",
        (cutoff, days),
    )
    deleted = result.rowcount
    conn.commit()
    conn.close()
    return jsonify({"deleted": deleted})


@app.route("/api/price/admin/delete-erroring", methods=["POST"])
@api_admin_required
def admin_delete_erroring():
    """Remove products with 3+ consecutive scraping failures."""
    conn = _get_db()
    result = conn.execute("DELETE FROM tracked_products WHERE error_count >= 3")
    deleted = result.rowcount
    conn.commit()
    conn.close()
    return jsonify({"deleted": deleted})


@app.route("/api/price/admin/delete-all-notified", methods=["POST"])
@api_admin_required
def admin_delete_all_notified():
    """Remove all notified products."""
    conn = _get_db()
    result = conn.execute("DELETE FROM tracked_products WHERE notified = 1")
    deleted = result.rowcount
    conn.commit()
    conn.close()
    return jsonify({"deleted": deleted})


@app.route("/api/price/admin/reset-errors/<product_id>", methods=["POST"])
@api_admin_required
def admin_reset_errors(product_id: str):
    """Reset error count for a product (retry scraping)."""
    conn = _get_db()
    conn.execute(
        "UPDATE tracked_products SET error_count = 0, last_error = '' WHERE id = ?",
        (product_id,),
    )
    conn.commit()
    conn.close()
    return jsonify({"ok": True})


@app.route("/api/price/admin/users")
@api_admin_required
def admin_users():
    """List all registered users with their product counts."""
    conn = _get_db()
    users = conn.execute(
        """SELECT u.username, u.created_at, u.is_admin,
                  COUNT(p.id) as product_count,
                  SUM(CASE WHEN p.notified = 0 THEN 1 ELSE 0 END) as active_count
           FROM users u
           LEFT JOIN tracked_products p ON u.username = p.username
           GROUP BY u.username
           ORDER BY u.created_at DESC"""
    ).fetchall()
    conn.close()
    return jsonify([dict(u) for u in users])


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    debug = os.environ.get("FLASK_DEBUG", "").lower() in ("1", "true", "yes")
    app.run(debug=debug, host="0.0.0.0", port=port)
