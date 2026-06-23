"""M5 (ADR-0013): self-hosted Cron trigger fires jobs on their croniter schedule."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from birdbot.runtime.cron import CronService

_BASE = datetime(2026, 6, 22, 0, 0, tzinfo=timezone.utc)


@pytest.mark.asyncio
async def test_fire_due_fires_due_job_once_and_reschedules():
    cron = CronService()
    fired: list[dict] = []

    async def on_job(job):
        fired.append(job.metadata)

    cron.on_job = on_job
    job = cron.add_job(cron="0 8 * * *", metadata={"tenant_id": "A", "date": "2026-06-22"})
    job.schedule(_BASE)  # next fire = 08:00

    assert await cron.fire_due(_BASE + timedelta(hours=1)) == 0  # 01:00 < 08:00
    assert fired == []

    assert await cron.fire_due(_BASE + timedelta(hours=9)) == 1  # 09:00 >= 08:00
    assert fired == [{"tenant_id": "A", "date": "2026-06-22"}]

    # rescheduled to the next day's 08:00 — not due again in the same window
    assert await cron.fire_due(_BASE + timedelta(hours=10)) == 0


@pytest.mark.asyncio
async def test_fire_due_noop_without_on_job_does_not_raise():
    cron = CronService()
    job = cron.add_job(cron="* * * * *", metadata={})
    job.schedule(_BASE)
    assert await cron.fire_due(_BASE + timedelta(minutes=2)) == 1  # counted, no on_job set


@pytest.mark.asyncio
async def test_start_runs_loop_and_fires_due_job_until_stopped():
    cron = CronService()
    fired: list[dict] = []

    async def on_job(job):
        fired.append(job.metadata)

    cron.on_job = on_job
    cron.add_job(cron="* * * * *", metadata={"k": "v"})

    calls = {"n": 0}

    async def fake_sleep(_seconds):
        calls["n"] += 1
        cron._running = False  # stop the loop after the first poll

    # clock 2 minutes past base -> the every-minute job is due on the first tick
    await cron.start(
        base=_BASE, clock=lambda: _BASE + timedelta(minutes=2), sleep=fake_sleep
    )
    assert cron._task is not None
    await cron._task  # let the run loop complete its single iteration

    assert fired == [{"k": "v"}]
    assert calls["n"] == 1
