"""Redis-backed (tenant, skill, model) quota limiter — production form of QuotaLimiter
(S16, ADR-0004).

Per-(tenant,skill,model) RPM window (INCR + EXPIRE) and concurrency slots, so a runaway
tenant only throttles its own key (fair-share). Async (Redis I/O); the in-memory
QuotaLimiter (#11) is the synchronous fast-path with the same semantics. Wire a
``redis.asyncio.Redis`` (or fakeredis) client in.
"""
from __future__ import annotations

from typing import Any

from birdbot.observability.quota import QuotaKey


class RedisQuotaLimiter:
    def __init__(
        self,
        client: Any,
        *,
        rpm: int = 60,
        max_concurrent: int = 4,
        window_seconds: int = 60,
    ) -> None:
        self._redis = client
        self._rpm = rpm
        self._max_concurrent = max_concurrent
        self._window = window_seconds

    @staticmethod
    def _base(key: QuotaKey) -> str:
        return f"{key.tenant_id}:{key.skill}:{key.model}"

    async def try_acquire(self, key: QuotaKey) -> bool:
        rpm_key = f"q:rpm:{self._base(key)}"
        count = await self._redis.incr(rpm_key)
        if count == 1:
            await self._redis.expire(rpm_key, self._window)
        if count > self._rpm:
            return False

        conc_key = f"q:conc:{self._base(key)}"
        concurrent = await self._redis.incr(conc_key)
        if concurrent > self._max_concurrent:
            await self._redis.decr(conc_key)
            return False
        return True

    async def release(self, key: QuotaKey) -> None:
        conc_key = f"q:conc:{self._base(key)}"
        current = await self._redis.get(conc_key)
        if current is not None and int(current) > 0:
            await self._redis.decr(conc_key)
