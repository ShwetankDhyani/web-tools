#!/usr/bin/env python3
"""
Standalone price checker — designed to be run by cron.

Executes once: checks all tracked products, updates prices,
sends Telegram alerts if below target, then exits cleanly.
No loops, no threads, no persistent state.

Usage:
    python3 check_prices.py

Cron example (every 3 minutes):
    */3 * * * * cd /path/to/web-tools && python3 check_prices.py >> /var/log/price_checker.log 2>&1
"""

import json
import logging
import os
import random
import sqlite3
import sys
import time
import urllib.parse
from datetime import datetime, timezone
from urllib.parse import urlparse

import requests

from scraper import scrape_price

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("price_checker")

# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "price_tracker.db")


def _get_db() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


# ---------------------------------------------------------------------------
# Telegram alerts (CallMeBot)
# ---------------------------------------------------------------------------

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


def _send_telegram_alert(product: dict, new_price: float) -> bool:
    """Send a Telegram alert via CallMeBot."""
    conn = _get_db()
    config = conn.execute("SELECT * FROM telegram_config WHERE id = 1").fetchone()
    conn.close()

    if not config or not config["enabled"] or not config["username"]:
        logger.info("Telegram not configured — skipping")
        return False

    short_url = _shorten_url(product['url'])
    text = (
        f"Price Drop Alert!\n\n"
        f"{product['name'] or 'Product'}\n"
        f"Current price: ${new_price:.2f}\n"
        f"Your target: ${product['target_price']:.2f}\n\n"
        f"{short_url}\n\n"
        f"- WebTools.wiki Price Tracker"
    )

    try:
        api_url = (
            f"https://api.callmebot.com/text.php"
            f"?user=@{urllib.parse.quote(config['username'])}"
            f"&text={urllib.parse.quote(text)}"
        )
        logger.info("Sending Telegram alert to @%s for '%s'", config["username"], product.get("name"))
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


# ---------------------------------------------------------------------------
# Main check
# ---------------------------------------------------------------------------

def check_all_prices():
    """Check prices for all un-notified tracked products, then exit."""
    conn = _get_db()
    products = conn.execute(
        "SELECT * FROM tracked_products WHERE notified = 0"
    ).fetchall()
    conn.close()

    if not products:
        logger.info("No products to check.")
        return

    logger.info("Checking %d product(s)...", len(products))

    for row in products:
        product = dict(row)
        url = product["url"]
        logger.info("Checking: %s", product.get("name") or url[:60])

        try:
            _, new_price = scrape_price(url)
        except Exception as e:
            new_price = None
            logger.error("Scrape exception for %s: %s", url[:80], e)

        now = datetime.now(timezone.utc).isoformat()
        conn = _get_db()

        if new_price is None:
            error_count = product.get("error_count", 0) + 1
            logger.warning("Could not get price for %s (fail #%d)", url[:80], error_count)
            conn.execute(
                """UPDATE tracked_products
                   SET error_count = ?, last_error = ?, last_checked = ?
                   WHERE id = ?""",
                (error_count, f"Failed to scrape price at {now}", now, product["id"]),
            )
            conn.commit()
            conn.close()
            continue

        history = json.loads(product["price_history"] or "[]")
        history.append({"price": new_price, "date": now})
        history = history[-100:]

        conn.execute(
            """UPDATE tracked_products
               SET current_price = ?, last_checked = ?, price_history = ?,
                   error_count = 0, last_error = ''
               WHERE id = ?""",
            (new_price, now, json.dumps(history), product["id"]),
        )

        if new_price <= product["target_price"]:
            logger.info("Price %.2f is at or below target %.2f!", new_price, product["target_price"])
            if _send_telegram_alert(product, new_price):
                conn.execute(
                    "UPDATE tracked_products SET notified = 1 WHERE id = ?",
                    (product["id"],),
                )

        conn.commit()
        conn.close()

        logger.info("  -> Price: %.2f (target: %.2f)", new_price, product["target_price"])

        # Humanized delay between products (1-4 seconds)
        if product != dict(products[-1]):
            delay = random.uniform(1.0, 4.0)
            time.sleep(delay)

    logger.info("Price check complete.")


if __name__ == "__main__":
    try:
        check_all_prices()
    except Exception as e:
        logger.error("Fatal error: %s", e, exc_info=True)
        sys.exit(1)
