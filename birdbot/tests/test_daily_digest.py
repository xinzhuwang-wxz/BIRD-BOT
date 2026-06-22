"""Integration tests for the daily digest (needs DB; skips without DSN).

Aggregate the day's events, enqueue the digest via the outbox (idempotent per
tenant+date), and wire nanobot's CronService (set on_job + start — the D5 gap)."""
from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest

from birdbot.digest.aggregate import aggregate_daily
from birdbot.digest.service import DailyDigestScheduler, run_daily_digest
from birdbot.workflow.outbox import Outbox

_DATE = "2026-06-22"
_TS = datetime(2026, 6, 22, 10, 0, tzinfo=timezone.utc)


async def _seed(app_db, species: str, *, event_id: str):
    async with app_db.tenant_scope("A") as conn:
        await conn.execute(
            """
            INSERT INTO events (tenant_id, device_id, event_id, kind, payload, created_at)
            VALUES ('A', 'd1', $1, 'bird_event', $2::jsonb, $3)
            """,
            event_id,
            json.dumps({"top_k": [{"label": species, "score": 0.9}]}),
            _TS,
        )


@pytest.mark.asyncio
async def test_aggregate_counts_events_and_species(app_db):
    await _seed(app_db, "robin", event_id="e1")
    await _seed(app_db, "robin", event_id="e2")
    await _seed(app_db, "sparrow", event_id="e3")

    digest = await aggregate_daily(app_db, tenant_id="A", date=_DATE)

    assert digest.event_count == 3
    assert digest.species_counts == {"robin": 2, "sparrow": 1}


@pytest.mark.asyncio
async def test_run_daily_digest_enqueues_to_outbox(app_db):
    await _seed(app_db, "robin", event_id="e1")
    await run_daily_digest(app_db, Outbox(app_db), tenant_id="A", date=_DATE)

    async with app_db.tenant_scope("A") as conn:
        row = await conn.fetchrow("SELECT topic, payload, dedupe_key FROM outbox")
    assert row["topic"] == "digest"
    assert json.loads(row["payload"])["event_count"] == 1
    assert row["dedupe_key"] == "digest:A:2026-06-22"


@pytest.mark.asyncio
async def test_run_daily_digest_is_idempotent(app_db):
    await _seed(app_db, "robin", event_id="e1")
    await run_daily_digest(app_db, Outbox(app_db), tenant_id="A", date=_DATE)
    await run_daily_digest(app_db, Outbox(app_db), tenant_id="A", date=_DATE)

    async with app_db.tenant_scope("A") as conn:
        assert await conn.fetchval("SELECT count(*) FROM outbox") == 1  # not re-enqueued


@pytest.mark.asyncio
async def test_scheduler_wires_on_job_and_starts(app_db, tmp_path):
    from nanobot.cron.service import CronService

    cron = CronService(store_path=tmp_path / "cron.json")
    assert cron.on_job is None  # kernel leaves it unwired (D5)

    scheduler = DailyDigestScheduler(cron, app_db, Outbox(app_db))
    assert cron.on_job is not None  # now wired

    try:
        await scheduler.start()
        assert cron._running is True  # explicitly started (kernel app never does)
    finally:
        if cron._timer_task is not None:
            cron._timer_task.cancel()
