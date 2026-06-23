"""Daily digest delivery + Cron wiring.

run_daily_digest aggregates and enqueues the digest to the outbox, idempotent per
tenant+date (it won't re-enqueue an already-queued digest). DailyDigestScheduler wires the
self-hosted CronService (ADR-0013) — setting on_job and calling start() so the trigger
actually fires; aggregation/state stay in Postgres (ADR-0002).
"""
from __future__ import annotations

from typing import Any

from birdbot.db.pool import Database
from birdbot.digest.aggregate import DailyDigest, aggregate_daily
from birdbot.workflow.outbox import Outbox


async def run_daily_digest(
    db: Database,
    outbox: Outbox,
    *,
    tenant_id: str,
    date: str,
    callback_topic: str = "digest",
) -> DailyDigest:
    digest = await aggregate_daily(db, tenant_id=tenant_id, date=date)
    dedupe_key = f"digest:{tenant_id}:{date}"
    async with db.tenant_scope(tenant_id) as conn:
        already = await conn.fetchval(
            "SELECT 1 FROM outbox WHERE dedupe_key = $1 LIMIT 1", dedupe_key
        )
        if already:
            return digest  # idempotent: this day's digest is already queued
        await outbox.enqueue(
            conn,
            tenant_id=tenant_id,
            topic=callback_topic,
            payload={
                "date": date,
                "event_count": digest.event_count,
                "species_counts": digest.species_counts,
            },
            dedupe_key=dedupe_key,
        )
    return digest


class DailyDigestScheduler:
    """Wires the self-hosted CronService (ADR-0013): sets on_job and starts it."""

    def __init__(
        self,
        cron_service: Any,
        db: Database,
        outbox: Outbox,
        *,
        callback_topic: str = "digest",
    ) -> None:
        self._cron = cron_service
        self._db = db
        self._outbox = outbox
        self._topic = callback_topic
        cron_service.on_job = self._on_job  # wire the trigger callback

    async def start(self) -> None:
        await self._cron.start()  # start the trigger loop

    async def _on_job(self, job: Any) -> str | None:
        metadata = getattr(job, "metadata", None) or {}
        tenant_id = metadata.get("tenant_id")
        date = metadata.get("date")
        if not tenant_id or not date:
            return None
        await run_daily_digest(
            self._db, self._outbox, tenant_id=tenant_id, date=date, callback_topic=self._topic
        )
        return None
