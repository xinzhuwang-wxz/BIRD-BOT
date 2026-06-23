"""G4: concurrency-correctness stress — governance / quota / RLS hold under concurrent load.

Not throughput/latency load testing (that needs a deployment target + load tool, a PRD #33
milestone). This stresses the multi-tenant invariants with asyncio.gather: telemetry
attribution doesn't cross-talk, quota fair-share isolates a noisy tenant, RLS isolates each
tenant — all under concurrency.

If real throughput/latency SLO load testing is needed, it belongs after a deployment target
exists (PRD #33); this file is the in-process concurrency-correctness gate.
"""
from __future__ import annotations

import asyncio

import pytest

from birdbot.observability.alerts import ListAlertSink
from birdbot.observability.telemetry import ListTelemetrySink
from birdbot.router.registry import CapabilityRegistry, ModelEntry
from birdbot.router.router import ModelRouter
from birdbot.runtime.gateway import LLMGateway
from birdbot.tenant.context import TenantEnvelope


class _AllowQuota:
    async def try_acquire(self, key):
        return True

    async def release(self, key):
        pass


def _registry():
    return CapabilityRegistry([
        ModelEntry(logical_name="m", backend="openai_compat", model="x",
                   capabilities=frozenset(), context_window=1000, pricing_per_mtok=1.0,
                   residency_region="US", compliance_tags=frozenset())
    ])


@pytest.mark.asyncio
async def test_gateway_concurrent_multitenant_telemetry_has_no_cross_talk():
    async def completion(*, model, messages, **kw):
        await asyncio.sleep(0)  # yield, interleave the concurrent calls
        return {"choices": [{"message": {"content": "ok"}}], "usage": {"total_tokens": 1}}

    tel = ListTelemetrySink()
    gw = LLMGateway(router=ModelRouter(_registry()), telemetry=tel, alerts=ListAlertSink(),
                    quota=_AllowQuota(), completion=completion)

    n = 40
    await asyncio.gather(*[
        gw.complete(envelope=TenantEnvelope(tenant_id=f"t{i}"), logical_model="m",
                    messages=[], skill="deep")
        for i in range(n)
    ])

    recorded = sorted(r.tenant_id for r in tel.records)
    assert len(tel.records) == n  # no lost / duplicated records under concurrency
    assert recorded == sorted(f"t{i}" for i in range(n))  # each tenant attributed correctly


@pytest.mark.asyncio
async def test_quota_concurrent_noisy_tenant_does_not_starve_others():
    import fakeredis.aioredis

    from birdbot.observability.quota import QuotaKey
    from birdbot.observability.redis_quota import RedisQuotaLimiter

    limiter = RedisQuotaLimiter(fakeredis.aioredis.FakeRedis(), rpm=3)
    noisy = QuotaKey("noisy", "deep", "m")
    quiet = QuotaKey("quiet", "deep", "m")

    granted = await asyncio.gather(*[limiter.try_acquire(noisy) for _ in range(12)])
    assert sum(granted) == 3  # noisy tenant capped at its own rpm

    assert await limiter.try_acquire(quiet) is True  # quiet tenant's bucket is unaffected


@pytest.mark.asyncio
async def test_rls_concurrent_multitenant_isolation(app_db):
    from birdbot.ingress.schema import BirdEvent
    from birdbot.ingress.store import EventStore

    store = EventStore(app_db)
    n = 20
    await asyncio.gather(*[
        store.accept(BirdEvent(tenant_id=f"t{i}", device_id="d", event_id=f"e{i}"))
        for i in range(n)
    ])

    async def own_count(tenant_id: str) -> int:
        async with app_db.tenant_scope(tenant_id) as conn:
            return await conn.fetchval("SELECT count(*) FROM events")

    counts = await asyncio.gather(*[own_count(f"t{i}") for i in range(n)])
    assert all(c == 1 for c in counts)  # RLS isolates each tenant even under concurrent writes
