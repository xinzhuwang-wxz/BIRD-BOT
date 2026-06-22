"""Integration tests for retention TTL purge (needs DB; skips without DSN).

Purge runs on the admin (superuser) connection, which bypasses RLS to sweep every
tenant's expired rows. Time is injected (no wall-clock)."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from birdbot.privacy.retention import purge_expired

_NOW = datetime(2026, 6, 22, tzinfo=timezone.utc)


@pytest.mark.asyncio
async def test_purge_deletes_expired_keeps_recent(app_db, admin_conn):
    async with app_db.tenant_scope("A") as conn:
        await conn.execute(
            "INSERT INTO events (tenant_id, kind, created_at) VALUES ('A', 'old', $1)",
            _NOW - timedelta(days=100),
        )
        await conn.execute(
            "INSERT INTO events (tenant_id, kind, created_at) VALUES ('A', 'new', $1)",
            _NOW - timedelta(days=1),
        )

    deleted = await purge_expired(admin_conn, now=_NOW, retention_days=90)

    assert deleted == 1
    async with app_db.tenant_scope("A") as conn:
        kinds = [r["kind"] for r in await conn.fetch("SELECT kind FROM events")]
    assert kinds == ["new"]


@pytest.mark.asyncio
async def test_purge_sweeps_across_tenants(app_db, admin_conn):
    for tenant in ("A", "B"):
        async with app_db.tenant_scope(tenant) as conn:
            await conn.execute(
                "INSERT INTO events (tenant_id, kind, created_at) VALUES ($1, 'old', $2)",
                tenant,
                _NOW - timedelta(days=200),
            )

    deleted = await purge_expired(admin_conn, now=_NOW, retention_days=90)
    assert deleted == 2  # admin (superuser) purges every tenant
