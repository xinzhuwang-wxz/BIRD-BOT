"""Nature Chat handler: drive the open-layer AgentRuntime for one chat turn.

Builds a per-request tenant-scoped tool registry whose lookups hit real backends: device
history from the events table (this device, last 30 days), local rarity from the Bird Context
Service (commercial=True, so eBird/iNat are intercepted pre-license — ADR-0005). Device/region
are bound deterministically, never LLM-settable (方案 §176). When a backend is absent the
lookup degrades to a safe default. One handler per process; one runtime + registry per request.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from birdbot.chat.registry import build_nature_chat_registry
from birdbot.runtime.agent import AgentRuntime
from birdbot.tenant.context import TenantEnvelope


def _utc_date() -> str:
    return datetime.now(timezone.utc).date().isoformat()


class NatureChatHandler:
    def __init__(self, *, gateway: Any, alerts: Any, db: Any = None, context_service: Any = None) -> None:
        self._gateway = gateway
        self._alerts = alerts
        self._db = db
        self._context = context_service

    async def handle(self, *, envelope: TenantEnvelope, prompt: str, region: str = "US") -> str:
        async def visits(species: str, device_id: str | None) -> dict[str, int]:
            if self._db is None or device_id is None:
                return {"visits_30d": 0}
            async with self._db.tenant_scope(envelope.tenant_id) as conn:
                n = await conn.fetchval(
                    "SELECT count(*) FROM events WHERE device_id = $1 "
                    "AND payload #>> '{top_k,0,label}' = $2 "
                    "AND created_at > now() - interval '30 days'",
                    device_id,
                    species,
                )
            return {"visits_30d": int(n or 0)}

        async def rarity(species: str, reg: str) -> str:
            if self._context is None:
                return "unknown"
            ctx = await self._context.get_context(region=reg, date=_utc_date(), commercial=True)
            return ctx.labels.get(species, "unknown")

        registry = build_nature_chat_registry(
            envelope=envelope, region=region, visits=visits, rarity=rarity
        )
        runtime = AgentRuntime(gateway=self._gateway, alerts=self._alerts)
        return await runtime.run(
            prompt=prompt, tools=registry.tools(), envelope=envelope, region=region
        )
