"""Integration tests for the Postgres + multi-tenant RLS foundation (issue #3).

Skips unless BIRDBOT_TEST_DATABASE_URL points at a throwaway Postgres (see conftest).
These exercise the real isolation boundary through the non-owner application role.
"""
from __future__ import annotations

import asyncpg
import pytest

from birdbot.db.migrations import apply_migrations


@pytest.mark.asyncio
async def test_migrations_are_idempotent(admin_conn):
    """Re-running migrations applies nothing new and leaves the schema in place."""
    again = await apply_migrations(admin_conn)
    assert again == []

    assert await admin_conn.fetchval("SELECT to_regclass('public.events')") is not None
    versions = {
        row["version"]
        for row in await admin_conn.fetch("SELECT version FROM schema_migrations")
    }
    assert "0001_init" in versions


@pytest.mark.asyncio
async def test_cross_tenant_reads_are_isolated(app_db):
    """A row written under tenant A is invisible to tenant B."""
    async with app_db.tenant_scope("A") as conn:
        await conn.execute(
            "INSERT INTO events (tenant_id, kind) VALUES ($1, $2)", "A", "visit"
        )

    async with app_db.tenant_scope("A") as conn:
        rows = await conn.fetch("SELECT id FROM events WHERE tenant_id = $1", "A")
        assert len(rows) == 1

    async with app_db.tenant_scope("B") as conn:
        # Even explicitly querying tenant A's rows, B must see nothing.
        rows = await conn.fetch("SELECT id FROM events WHERE tenant_id = $1", "A")
        assert rows == []


@pytest.mark.asyncio
async def test_missing_where_clause_is_still_filtered_by_rls(app_db):
    """A query that forgets WHERE tenant_id still only sees the current tenant's rows."""
    async with app_db.tenant_scope("A") as conn:
        await conn.execute("INSERT INTO events (tenant_id, kind) VALUES ($1, $2)", "A", "visit")
    async with app_db.tenant_scope("B") as conn:
        await conn.execute("INSERT INTO events (tenant_id, kind) VALUES ($1, $2)", "B", "visit")

    async with app_db.tenant_scope("A") as conn:
        total = await conn.fetchval("SELECT count(*) FROM events")  # no WHERE clause
        assert total == 1
        seen = {row["tenant_id"] for row in await conn.fetch("SELECT tenant_id FROM events")}
        assert seen == {"A"}


@pytest.mark.asyncio
async def test_unscoped_connection_is_fail_closed(app_db, unscoped_app_conn):
    """A connection that never set app.current_tenant sees nothing and cannot insert."""
    async with app_db.tenant_scope("A") as conn:
        await conn.execute("INSERT INTO events (tenant_id, kind) VALUES ($1, $2)", "A", "visit")

    assert await unscoped_app_conn.fetch("SELECT id FROM events") == []
    with pytest.raises(asyncpg.PostgresError):
        await unscoped_app_conn.execute(
            "INSERT INTO events (tenant_id, kind) VALUES ($1, $2)", "A", "visit"
        )


@pytest.mark.asyncio
async def test_cannot_write_outside_current_tenant(app_db):
    """WITH CHECK blocks writing a row for a tenant other than the scoped one."""
    with pytest.raises(asyncpg.PostgresError):
        async with app_db.tenant_scope("A") as conn:
            await conn.execute(
                "INSERT INTO events (tenant_id, kind) VALUES ($1, $2)", "B", "spoof"
            )
