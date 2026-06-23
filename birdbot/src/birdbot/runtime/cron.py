"""Self-hosted Cron trigger (ADR-0013 / M5): replaces nanobot's CronService.

Cron is only the trigger (ADR-0002) — aggregation/state live in Postgres. Each job carries
metadata (e.g. tenant_id/date); ``on_job`` is wired by the app (e.g. DailyDigestScheduler)
and fired when a job's croniter schedule comes due. ``clock``/``sleep`` are injectable so the
fire logic is deterministically testable without real time.
"""
from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from datetime import datetime, timezone
from typing import Any

from croniter import croniter


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class CronJob:
    def __init__(self, *, cron: str, metadata: dict[str, Any]) -> None:
        self.cron = cron
        self.metadata = metadata
        self._next: datetime | None = None

    def schedule(self, base: datetime) -> None:
        """Compute the next fire time strictly after ``base``."""
        self._next = croniter(self.cron, base).get_next(datetime)

    def is_due(self, now: datetime) -> bool:
        return self._next is not None and now >= self._next


class CronService:
    """Fires registered jobs when their cron schedule comes due; ``on_job`` set by the app."""

    def __init__(self) -> None:
        self.on_job: Callable[[CronJob], Awaitable[Any]] | None = None
        self._jobs: list[CronJob] = []
        self._running = False
        self._task: asyncio.Task[Any] | None = None
        self._poll_seconds = 30.0

    def add_job(self, *, cron: str, metadata: dict[str, Any]) -> CronJob:
        job = CronJob(cron=cron, metadata=metadata)
        self._jobs.append(job)
        return job

    async def fire_due(self, now: datetime) -> int:
        """Fire (and reschedule) every job due at/before ``now``; returns how many fired."""
        fired = 0
        for job in self._jobs:
            if job.is_due(now):
                if self.on_job is not None:
                    await self.on_job(job)
                job.schedule(now)
                fired += 1
        return fired

    async def start(
        self,
        *,
        base: datetime | None = None,
        clock: Callable[[], datetime] | None = None,
        sleep: Callable[[float], Awaitable[None]] | None = None,
    ) -> None:
        resolved_clock = clock or _utcnow
        for job in self._jobs:
            job.schedule(base or resolved_clock())
        self._running = True
        self._task = asyncio.create_task(self._run(resolved_clock, sleep or asyncio.sleep))

    async def _run(
        self, clock: Callable[[], datetime], sleep: Callable[[float], Awaitable[None]]
    ) -> None:
        while self._running:
            await sleep(self._poll_seconds)
            await self.fire_due(clock())

    async def stop(self) -> None:
        self._running = False
        if self._task is not None:
            self._task.cancel()
            self._task = None
