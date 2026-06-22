"""(tenant, skill, model) quota / rate limiting with fair-share isolation (ADR-0004).

Each (tenant, skill, model) triple has its own RPM window + concurrency slots, so a
runaway tenant only throttles its own key and can't starve others. In-memory MVP with an
injected clock (a Redis-backed bucket is the production form; same interface).
"""
from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass

_WINDOW_SECONDS = 60.0


@dataclass(frozen=True, slots=True)
class QuotaKey:
    tenant_id: str
    skill: str
    model: str


class QuotaLimiter:
    def __init__(
        self,
        *,
        rpm: int = 60,
        max_concurrent: int = 4,
        now: Callable[[], float] = time.monotonic,
    ) -> None:
        self._rpm = rpm
        self._max_concurrent = max_concurrent
        self._now = now
        self._windows: dict[QuotaKey, tuple[float, int]] = {}
        self._concurrent: dict[QuotaKey, int] = {}

    def try_acquire(self, key: QuotaKey) -> bool:
        now = self._now()
        start, count = self._windows.get(key, (now, 0))
        if now - start >= _WINDOW_SECONDS:
            start, count = now, 0  # new window
        if count >= self._rpm:
            return False
        if self._concurrent.get(key, 0) >= self._max_concurrent:
            return False
        self._windows[key] = (start, count + 1)
        self._concurrent[key] = self._concurrent.get(key, 0) + 1
        return True

    def release(self, key: QuotaKey) -> None:
        self._concurrent[key] = max(0, self._concurrent.get(key, 0) - 1)
