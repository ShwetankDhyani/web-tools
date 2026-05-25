"""Log price-check iterations for admin reporting."""

import os
import sqlite3
from datetime import datetime, timezone

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "price_tracker.db")


def log_check_run(
    product_id: str,
    success: bool,
    *,
    price: float | None = None,
    error: str | None = None,
    source: str = "cron",
) -> None:
    """Record one tracking iteration (cron, manual, or initial scrape)."""
    now = datetime.now(timezone.utc).isoformat()
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute(
        """INSERT INTO check_runs (product_id, checked_at, success, price, error, source)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (product_id, now, 1 if success else 0, price, error, source),
    )
    conn.commit()
    conn.close()
