"""Unit tests for the Redis-backed quota limiter (S16), using fakeredis (no docker redis).

Same fair-share semantics as the in-memory QuotaLimiter (#11): per-(tenant,skill,model)
buckets, so a runaway tenant only throttles its own key."""
from __future__ import annotations

import fakeredis.aioredis
import pytest

from birdbot.observability.quota import QuotaKey
from birdbot.observability.redis_quota import RedisQuotaLimiter


@pytest.fixture
def redis_client():
    return fakeredis.aioredis.FakeRedis()


@pytest.mark.asyncio
async def test_per_key_rpm_limit(redis_client):
    q = RedisQuotaLimiter(redis_client, rpm=2)
    key = QuotaKey("A", "story", "opus")
    assert await q.try_acquire(key)
    assert await q.try_acquire(key)
    assert not await q.try_acquire(key)


@pytest.mark.asyncio
async def test_one_tenant_maxed_does_not_starve_another(redis_client):
    q = RedisQuotaLimiter(redis_client, rpm=1)
    a = QuotaKey("A", "story", "opus")
    b = QuotaKey("B", "story", "opus")
    assert await q.try_acquire(a)
    assert not await q.try_acquire(a)
    assert await q.try_acquire(b)  # independent bucket


@pytest.mark.asyncio
async def test_concurrency_limit_and_release(redis_client):
    q = RedisQuotaLimiter(redis_client, rpm=100, max_concurrent=1)
    key = QuotaKey("A", "s", "m")
    assert await q.try_acquire(key)
    assert not await q.try_acquire(key)
    await q.release(key)
    assert await q.try_acquire(key)
