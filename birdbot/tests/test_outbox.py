"""Integration tests for the transactional outbox (needs DB; skips without DSN).

enqueue rides the caller's tenant-scoped transaction (same-transaction commit with the
business write); relay is a system sweep over a non-owner-bypassing (owner) connection.
"""
from __future__ import annotations

import pytest

from birdbot.workflow.outbox import Outbox, relay


@pytest.mark.asyncio
async def test_enqueue_commits_with_the_business_write(app_db):
    outbox = Outbox(app_db)
    async with app_db.tenant_scope("A") as conn:
        await conn.execute("INSERT INTO events (tenant_id, kind) VALUES ('A', 'x')")
        await outbox.enqueue(conn, tenant_id="A", topic="callback", payload={"job": "1"})

    async with app_db.tenant_scope("A") as conn:
        assert await conn.fetchval("SELECT count(*) FROM outbox") == 1
        assert await conn.fetchval("SELECT count(*) FROM events") == 1


@pytest.mark.asyncio
async def test_enqueue_rolls_back_with_the_business_write(app_db):
    """If the business transaction aborts, the outbox row is gone too (no dual write)."""
    outbox = Outbox(app_db)
    with pytest.raises(RuntimeError):
        async with app_db.tenant_scope("A") as conn:
            await conn.execute("INSERT INTO events (tenant_id, kind) VALUES ('A', 'x')")
            await outbox.enqueue(
                conn, tenant_id="A", topic="callback", payload={"job": "1"}
            )
            raise RuntimeError("boom")  # abort the transaction

    async with app_db.tenant_scope("A") as conn:
        assert await conn.fetchval("SELECT count(*) FROM outbox") == 0
        assert await conn.fetchval("SELECT count(*) FROM events") == 0


@pytest.mark.asyncio
async def test_relay_delivers_pending_once(app_db, admin_conn):
    outbox = Outbox(app_db)
    async with app_db.tenant_scope("A") as conn:
        await outbox.enqueue(
            conn, tenant_id="A", topic="callback", payload={"job": "1"}, dedupe_key="A:1"
        )

    received = []

    async def deliver(msg):
        received.append(msg)

    assert await relay(admin_conn, deliver) == 1
    assert received[0]["tenant_id"] == "A"
    assert received[0]["payload"] == {"job": "1"}
    # nothing pending the second time — delivered rows are not re-sent
    assert await relay(admin_conn, deliver) == 0
    assert len(received) == 1


@pytest.mark.asyncio
async def test_relay_keeps_row_pending_when_delivery_fails(app_db, admin_conn):
    """at-least-once: a failed delivery leaves the row pending for the next relay."""
    outbox = Outbox(app_db)
    async with app_db.tenant_scope("A") as conn:
        await outbox.enqueue(conn, tenant_id="A", topic="callback", payload={"job": "1"})

    async def failing(msg):
        raise RuntimeError("webhook down")

    assert await relay(admin_conn, failing) == 0  # nothing delivered

    ok = []

    async def ok_deliver(msg):
        ok.append(msg)

    assert await relay(admin_conn, ok_deliver) == 1  # retried and delivered
    assert len(ok) == 1


@pytest.mark.asyncio
async def test_consumer_dedupes_at_least_once_redeliveries():
    """An at-least-once redelivery of the same logical event is handled once."""
    processed: set[str] = set()
    handled: list[str] = []

    async def idempotent_consumer(msg):
        key = msg["dedupe_key"]
        if key in processed:
            return
        processed.add(key)
        handled.append(key)

    await idempotent_consumer({"dedupe_key": "A:job:1"})
    await idempotent_consumer({"dedupe_key": "A:job:1"})  # redelivery

    assert handled == ["A:job:1"]
