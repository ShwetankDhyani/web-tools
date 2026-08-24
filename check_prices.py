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
from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse

import requests

from price_log import record_price_check
from scraper import currency_from_url, scrape_price

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
        logger.info("Sending Telegram alert to @%s for '%s'", username, product.get("name"))
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

def _is_due(product: dict, now: datetime) -> bool:
    interval = product.get("check_interval") or 3
    try:
        interval = max(2, min(60, int(interval)))
    except (TypeError, ValueError):
        interval = 3

    last = product.get("last_checked")
    if not last:
        return True
    try:
        last_dt = datetime.fromisoformat(last.replace("Z", "+00:00"))
        if last_dt.tzinfo is None:
            last_dt = last_dt.replace(tzinfo=timezone.utc)
    except ValueError:
        return True
    return now >= last_dt + timedelta(minutes=interval)


def check_all_prices():
    """Check prices for due tracked products, then exit.

    Products stay monitored after an alert. If price rises above the target,
    `notified` resets so a later drop can alert again.
    """
    conn = _get_db()
    products = conn.execute("SELECT * FROM tracked_products").fetchall()
    conn.close()

    if not products:
        logger.info("No products to check.")
        return

    now = datetime.now(timezone.utc)
    due = [dict(row) for row in products if _is_due(dict(row), now)]

    if not due:
        logger.info("No products due for checking (%d total tracked).", len(products))
        return

    logger.info("Checking %d product(s) (of %d total)...", len(due), len(products))

    for i, product in enumerate(due):
        url = product["url"]
        logger.info("Checking: %s", product.get("name") or url[:60])

        scrape_error = None
        try:
            _, new_price, scraped_currency, resolved_url = scrape_price(url)
        except Exception as e:
            new_price = None
            scrape_error = str(e)
            logger.error("Scrape exception for %s: %s", url[:80], e)

        now = datetime.now(timezone.utc).isoformat()
        conn = _get_db()

        if new_price is None:
            error_count = product.get("error_count", 0) + 1
            err_msg = scrape_error or f"Failed to scrape price at {now}"
            logger.warning("Could not get price for %s (fail #%d)", url[:80], error_count)
            conn.execute(
                """UPDATE tracked_products
                   SET error_count = ?, last_error = ?, last_checked = ?
                   WHERE id = ?""",
                (error_count, err_msg, now, product["id"]),
            )
            record_price_check(
                product["id"], False, error=err_msg, source="cron", conn=conn
            )
            conn.commit()
            conn.close()
            if i < len(due) - 1:
                time.sleep(random.uniform(1.0, 4.0))
            continue

        history = json.loads(product["price_history"] or "[]")
        history.append({"price": new_price, "date": now})
        history = history[-100:]

        store_url = resolved_url or url
        currency = scraped_currency or product.get("currency") or currency_from_url(store_url)
        conn.execute(
            """UPDATE tracked_products
               SET current_price = ?, last_checked = ?, price_history = ?,
                   error_count = 0, last_error = '', currency = ?, url = ?
               WHERE id = ?""",
            (new_price, now, json.dumps(history), currency, store_url, product["id"]),
        )
        product["currency"] = currency
        record_price_check(
            product["id"], True, price=new_price, source="cron", conn=conn
        )

        if new_price <= product["target_price"]:
            logger.info("Price %.2f is at or below target %.2f!", new_price, product["target_price"])
            if not product.get("notified"):
                if _send_telegram_alert(product, new_price):
                    conn.execute(
                        "UPDATE tracked_products SET notified = 1 WHERE id = ?",
                        (product["id"],),
                    )
        else:
            # Price recovered above target — allow a future drop to alert again
            if product.get("notified"):
                logger.info("Price recovered above target; resetting notified flag")
                conn.execute(
                    "UPDATE tracked_products SET notified = 0 WHERE id = ?",
                    (product["id"],),
                )

        conn.commit()
        conn.close()

        logger.info("  -> Price: %.2f (target: %.2f)", new_price, product["target_price"])

        if i < len(due) - 1:
            time.sleep(random.uniform(1.0, 4.0))

    logger.info("Price check complete.")


if __name__ == "__main__":
    try:
        check_all_prices()
    except Exception as e:
        logger.error("Fatal error: %s", e, exc_info=True)
        sys.exit(1)
