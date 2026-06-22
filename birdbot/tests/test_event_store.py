"""Integration tests for EventStore (needs a DB; skips without BIRDBOT_TEST_DATABASE_URL)."""
from __future__ import annotations

import pytest

from birdbot.ingress.schema import BirdEvent
from birdbot.ingress.store import EventStore


@pytest.mark.asyncio
async def test_accept_lands_queued_event_and_returns_job(app_db):
    store = EventStore(app_db)
    event = BirdEvent(
        tenant_id="A", device_id="d1", event_id="e1", media=["https://cdn/i.jpg"]
    )

    result = await store.accept(event)

    assert result.job_id is not None
    assert result.status == "queued"
    assert result.duplicate is False
    assert await store.job_status("A", result.job_id) == "queued"


@pytest.mark.asyncio
async def test_duplicate_submission_is_idempotent(app_db):
    store = EventStore(app_db)
    event = BirdEvent(tenant_id="A", device_id="d1", event_id="e1")

    first = await store.accept(event)
    second = await store.accept(event)

    assert second.job_id == first.job_id
    assert second.duplicate is True
    async with app_db.tenant_scope("A") as conn:
        assert await conn.fetchval("SELECT count(*) FROM events") == 1
