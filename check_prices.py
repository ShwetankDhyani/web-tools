#!/usr/bin/env python3
"""
Standalone price checker — designed to be run by cron.

Executes once: checks all tracked products, updates prices,
sends alerts if below target, then exits cleanly.
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
import smtplib
import sqlite3
import sys
import time
import urllib.parse
from datetime import datetime, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

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
# Email alerts
# ---------------------------------------------------------------------------

def _send_price_alert(product: dict, new_price: float) -> bool:
    """Send an email alert about a price drop."""
    conn = _get_db()
    config = conn.execute("SELECT * FROM email_config WHERE id = 1").fetchone()
    conn.close()

    if not config or not config["smtp_user"] or not config["smtp_pass"]:
        logger.warning("Email not configured — skipping alert for %s", product.get("name"))
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
                Sent by WebTools.wiki Price Tracker
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
        logger.info("Alert sent to %s for '%s' (price: %.2f)", product["email"], product["name"], new_price)
        return True
    except Exception as e:
        logger.error("Failed to send email to %s: %s", product["email"], e)
        return False


# ---------------------------------------------------------------------------
# WhatsApp alerts (CallMeBot)
# ---------------------------------------------------------------------------

def _send_whatsapp_alert(product: dict, new_price: float) -> bool:
    """Send a WhatsApp alert via CallMeBot."""
    conn = _get_db()
    config = conn.execute("SELECT * FROM whatsapp_config WHERE id = 1").fetchone()
    conn.close()

    if not config or not config["phone"] or not config["api_key"] or not config["enabled"]:
        return False

    text = (
        f"\U0001f4c9 *Price Drop Alert!*\n\n"
        f"*{product['name'] or 'Product'}*\n"
        f"Current price: *${new_price:.2f}*\n"
        f"Your target: ${product['target_price']:.2f}\n\n"
        f"{product['url']}\n\n"
        f"\u2014 WebTools.wiki Price Tracker"
    )

    try:
        api_url = (
            f"https://api.callmebot.com/whatsapp.php"
            f"?phone={urllib.parse.quote(config['phone'])}"
            f"&text={urllib.parse.quote(text)}"
            f"&apikey={urllib.parse.quote(config['api_key'])}"
        )
        resp = requests.get(api_url, timeout=15)
        if resp.status_code == 200:
            logger.info("WhatsApp alert sent to %s for '%s'", config["phone"], product.get("name"))
            return True
        else:
            logger.warning("WhatsApp API returned status %d", resp.status_code)
            return False
    except Exception as e:
        logger.error("Failed to send WhatsApp alert: %s", e)
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

        _, new_price = scrape_price(url)

        if new_price is None:
            logger.warning("Could not get price for %s", url[:80])
            continue

        now = datetime.now(timezone.utc).isoformat()
        history = json.loads(product["price_history"] or "[]")
        history.append({"price": new_price, "date": now})
        history = history[-100:]

        conn = _get_db()
        conn.execute(
            """UPDATE tracked_products
               SET current_price = ?, last_checked = ?, price_history = ?
               WHERE id = ?""",
            (new_price, now, json.dumps(history), product["id"]),
        )

        if new_price <= product["target_price"]:
            logger.info("Price %.2f is at or below target %.2f!", new_price, product["target_price"])
            email_sent = _send_price_alert(product, new_price)
            _send_whatsapp_alert(product, new_price)
            if email_sent:
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
