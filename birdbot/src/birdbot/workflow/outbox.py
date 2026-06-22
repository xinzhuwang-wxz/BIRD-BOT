"""Transactional outbox (ADR-0002): resolve the dual-write between a business commit
and an external callback.

enqueue runs on the caller's connection — inside their tenant-scoped transaction — so
the outbox row commits atomically with the business write. A separate relay (a system
sweep on an owner connection, since outbox RLS is ENABLE-not-FORCE) delivers pending
rows at-least-once; the consumer dedupes redeliveries by dedupe_key.
"""
from __future__ import annotations

import json
from collections.abc import Awaitable, Callable
from typing import Any

from birdbot.db.pool import Database


class Outbox:
    def __init__(self, db: Database) -> None:
        self._db = db

    async def enqueue(
        self,
        conn: Any,
        *,
        tenant_id: str,
        topic: str,
        payload: dict[str, Any],
        dedupe_key: str | None = None,
    ) -> None:
        """Insert an outbox row using the caller's (transaction-bound) connection."""
        await conn.execute(
            """
            INSERT INTO outbox (tenant_id, topic, payload, dedupe_key)
            VALUES ($1, $2, $3::jsonb, $4)
            """,
            tenant_id,
            topic,
            json.dumps(payload),
            dedupe_key,
        )


async def relay(
    conn: Any,
    deliver: Callable[[dict[str, Any]], Awaitable[None]],
    *,
    limit: int = 100,
) -> int:
    """Deliver pending outbox rows at-least-once; return how many were delivered.

    Runs on a system (owner) connection that bypasses RLS so it sweeps every tenant. A
    row is marked delivered only after ``deliver`` succeeds; a failed delivery leaves it
    pending for the next relay (at-least-once — the consumer dedupes by dedupe_key).
    """
    rows = await conn.fetch(
        """
        SELECT id, tenant_id, topic, payload, dedupe_key
        FROM outbox WHERE status = 'pending' ORDER BY id LIMIT $1
        """,
        limit,
    )
    delivered = 0
    for row in rows:
        msg = {
            "tenant_id": row["tenant_id"],
            "topic": row["topic"],
            "payload": json.loads(row["payload"]),
            "dedupe_key": row["dedupe_key"],
        }
        try:
            await deliver(msg)
        except Exception:
            await conn.execute(
                "UPDATE outbox SET attempts = attempts + 1 WHERE id = $1", row["id"]
            )
            continue
        await conn.execute(
            """
            UPDATE outbox
            SET status = 'delivered', delivered_at = now(), attempts = attempts + 1
            WHERE id = $1
            """,
            row["id"],
        )
        delivered += 1
    return delivered
