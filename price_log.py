"""Log price-check iterations and increment per-product check counter."""

import os
import sqlite3
from datetime import datetime, timezone

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "price_tracker.db")


def record_price_check(
    product_id: str,
    success: bool,
    *,
    price: float | None = None,
    error: str | None = None,
    source: str = "cron",
    conn: sqlite3.Connection | None = None,
) -> None:
    """Increment check_count and append to check_runs for every price retrieval attempt."""
    now = datetime.now(timezone.utc).isoformat()
    own_conn = conn is None
    if own_conn:
        conn = sqlite3.connect(DB_PATH)
        conn.execute("PRAGMA foreign_keys = ON")

    conn.execute(
        "UPDATE tracked_products SET check_count = COALESCE(check_count, 0) + 1 WHERE id = ?",
        (product_id,),
    )
    try:
        conn.execute(
            """INSERT INTO check_runs (product_id, checked_at, success, price, error, source)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (product_id, now, 1 if success else 0, price, error, source),
        )
    except sqlite3.OperationalError:
        pass  # check_runs table may not exist yet; counter still updated

    if own_conn:
        conn.commit()
        conn.close()


def log_check_run(
    product_id: str,
    success: bool,
    *,
    price: float | None = None,
    error: str | None = None,
    source: str = "cron",
) -> None:
    record_price_check(
        product_id, success, price=price, error=error, source=source, conn=None
    )
