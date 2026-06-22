"""Retention TTLs + expiry purge (方案 §9 / GDPR data minimization).

Each data class has a retention window; the purge deletes rows past it. Purge is a
system task: run it on an admin (superuser) connection, which bypasses RLS to sweep
every tenant. Time is injected so the task is testable without wall-clock.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

# Retention windows (days). events is the seed business table; media/session stores
# carry their own windows where they live.
RETENTION_DAYS: dict[str, int] = {
    "events": 90,
}


def _affected(status: str) -> int:
    # asyncpg execute() returns a command tag like "DELETE 3".
    return int(status.split()[-1]) if status else 0


async def purge_expired(
    conn: Any,
    *,
    now: datetime,
    retention_days: int = RETENTION_DAYS["events"],
) -> int:
    """Delete events older than the retention window; return the row count."""
    cutoff = now - timedelta(days=retention_days)
    status = await conn.execute("DELETE FROM events WHERE created_at < $1", cutoff)
    return _affected(status)
