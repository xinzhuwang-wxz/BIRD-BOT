"""Aggregate one day's events into a digest (tenant-scoped; RLS confines the query)."""
from __future__ import annotations

from dataclasses import dataclass

from birdbot.db.pool import Database


@dataclass(frozen=True, slots=True)
class DailyDigest:
    tenant_id: str
    date: str
    event_count: int
    species_counts: dict[str, int]


async def aggregate_daily(db: Database, *, tenant_id: str, date: str) -> DailyDigest:
    async with db.tenant_scope(tenant_id) as conn:
        rows = await conn.fetch(
            """
            SELECT payload #>> '{top_k,0,label}' AS species, count(*) AS n
            FROM events
            WHERE created_at::date = $1::text::date
            GROUP BY species
            """,
            date,
        )
    species_counts = {row["species"]: row["n"] for row in rows if row["species"]}
    event_count = sum(row["n"] for row in rows)
    return DailyDigest(tenant_id, date, event_count, species_counts)
