"""Integration tests for DSAR cascade delete/export (needs DB; skips without DSN).

Runs through tenant_scope (app role), so RLS guarantees a DSAR request for one tenant
can never touch another — even though the delete doesn't name tenant_id."""
from __future__ import annotations

import pytest

from birdbot.privacy.dsar import delete_subject, export_subject


@pytest.mark.asyncio
async def test_delete_subject_by_user_within_tenant(app_db):
    async with app_db.tenant_scope("A") as conn:
        await conn.execute(
            "INSERT INTO events (tenant_id, user_id, device_id, kind) VALUES ('A','u1','d1','x')"
        )
        await conn.execute(
            "INSERT INTO events (tenant_id, user_id, device_id, kind) VALUES ('A','u2','d2','y')"
        )

    deleted = await delete_subject(app_db, tenant_id="A", user_id="u1")

    assert deleted == 1
    async with app_db.tenant_scope("A") as conn:
        users = {r["user_id"] for r in await conn.fetch("SELECT user_id FROM events")}
    assert users == {"u2"}


@pytest.mark.asyncio
async def test_dsar_is_tenant_isolated(app_db):
    async with app_db.tenant_scope("A") as conn:
        await conn.execute("INSERT INTO events (tenant_id, user_id, kind) VALUES ('A','u1','x')")
    async with app_db.tenant_scope("B") as conn:
        await conn.execute("INSERT INTO events (tenant_id, user_id, kind) VALUES ('B','u1','x')")

    await delete_subject(app_db, tenant_id="A", user_id="u1")

    async with app_db.tenant_scope("B") as conn:
        assert await conn.fetchval("SELECT count(*) FROM events") == 1  # tenant B intact


@pytest.mark.asyncio
async def test_delete_whole_tenant_when_subject_unscoped(app_db):
    async with app_db.tenant_scope("A") as conn:
        await conn.execute("INSERT INTO events (tenant_id, user_id, kind) VALUES ('A','u1','x')")
        await conn.execute("INSERT INTO events (tenant_id, user_id, kind) VALUES ('A','u2','y')")

    deleted = await delete_subject(app_db, tenant_id="A")  # no user/device → whole tenant

    assert deleted == 2
    async with app_db.tenant_scope("A") as conn:
        assert await conn.fetchval("SELECT count(*) FROM events") == 0


@pytest.mark.asyncio
async def test_export_subject_returns_rows(app_db):
    async with app_db.tenant_scope("A") as conn:
        await conn.execute(
            "INSERT INTO events (tenant_id, user_id, kind) VALUES ('A','u1','visit')"
        )

    rows = await export_subject(app_db, tenant_id="A", user_id="u1")
    assert len(rows) == 1
    assert rows[0]["kind"] == "visit"
