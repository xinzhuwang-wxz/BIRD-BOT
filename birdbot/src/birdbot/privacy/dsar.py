"""DSAR (data subject access request): cascade delete/export by tenant/user/device.

Runs through the tenant-scoped Database (app role), so RLS confines every DSAR to its
tenant even though the queries don't name tenant_id — a forgotten tenant filter cannot
leak across tenants (that's the RLS guarantee). user_id/device_id of None widen to the
whole tenant. Covers events (the primary business table); other tables cascade once they
carry a subject linkage (later slice).
"""
from __future__ import annotations

from typing import Any

from birdbot.db.pool import Database

_SUBJECT_FILTER = """
    ($1::text IS NULL OR user_id = $1)
    AND ($2::text IS NULL OR device_id = $2)
"""


async def delete_subject(
    db: Database,
    *,
    tenant_id: str,
    user_id: str | None = None,
    device_id: str | None = None,
) -> int:
    async with db.tenant_scope(tenant_id) as conn:
        status = await conn.execute(
            f"DELETE FROM events WHERE {_SUBJECT_FILTER}", user_id, device_id
        )
        return int(status.split()[-1]) if status else 0


async def export_subject(
    db: Database,
    *,
    tenant_id: str,
    user_id: str | None = None,
    device_id: str | None = None,
) -> list[dict[str, Any]]:
    async with db.tenant_scope(tenant_id) as conn:
        rows = await conn.fetch(
            f"SELECT job_id, kind, payload, created_at FROM events WHERE {_SUBJECT_FILTER}",
            user_id,
            device_id,
        )
        return [dict(row) for row in rows]
