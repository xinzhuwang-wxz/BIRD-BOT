"""EventStore — lands BirdEvents in Postgres and answers status queries.

Uses the tenant-scoped Database (RLS-enforced) so every write/read is confined to the
event's tenant. The acceptance path is the deep-module A1 tail: validated event ->
idempotency key -> queued row -> job handle.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from birdbot.db.pool import Database
from birdbot.ingress.schema import BirdEvent

_KIND = "bird_event"


@dataclass(frozen=True, slots=True)
class AcceptResult:
    """Outcome of accepting a BirdEvent: the public job handle + whether it was a dup."""

    job_id: UUID
    status: str
    duplicate: bool


class EventStore:
    def __init__(self, db: Database) -> None:
        self._db = db

    @staticmethod
    def _payload(event: BirdEvent) -> str:
        return json.dumps(
            {
                "schema_version": event.schema_version,
                "media": event.media,
                "top_k": [c.model_dump() for c in event.top_k],
                "location": event.location.model_dump() if event.location else None,
            }
        )

    async def accept(self, event: BirdEvent) -> AcceptResult:
        """Land the event as a queued job under its tenant; return the job handle.

        Idempotent on the (tenant, device, event) key: a repeat submission does not
        create a second row and returns the original job handle with duplicate=True.
        """
        async with self._db.tenant_scope(event.tenant_id) as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO events (tenant_id, user_id, device_id, event_id, kind, payload)
                VALUES ($1, $2, $3, $4, $5, $6::jsonb)
                ON CONFLICT (tenant_id, device_id, event_id) DO NOTHING
                RETURNING job_id, status
                """,
                event.tenant_id,
                event.user_id,
                event.device_id,
                event.event_id,
                _KIND,
                self._payload(event),
            )
            if row is not None:
                return AcceptResult(
                    job_id=row["job_id"], status=row["status"], duplicate=False
                )
            existing = await conn.fetchrow(
                """
                SELECT job_id, status FROM events
                WHERE tenant_id = $1 AND device_id = $2 AND event_id = $3
                """,
                event.tenant_id,
                event.device_id,
                event.event_id,
            )
            return AcceptResult(
                job_id=existing["job_id"], status=existing["status"], duplicate=True
            )

    async def job_status(self, tenant_id: str, job_id: str | UUID) -> str | None:
        """Return the job's status within ``tenant_id``, or None if not visible."""
        async with self._db.tenant_scope(tenant_id) as conn:
            row = await conn.fetchrow(
                "SELECT status FROM events WHERE job_id = $1::uuid", str(job_id)
            )
            return row["status"] if row else None

    async def attach_fast_snapshot(
        self, *, tenant_id: str, device_id: str, event_id: str, snapshot: dict[str, Any]
    ) -> None:
        """Merge the fast-stage snapshot into the event's payload (deep-stage input)."""
        async with self._db.tenant_scope(tenant_id) as conn:
            await conn.execute(
                """
                UPDATE events SET payload = payload || $3::jsonb
                WHERE device_id = $1 AND event_id = $2
                """,
                device_id,
                event_id,
                json.dumps({"fast_stage": snapshot}),
            )
