"""Integration tests for WorkflowRuntime (needs DB; skips without BIRDBOT_TEST_DATABASE_URL)."""
from __future__ import annotations

import asyncio
import json

import pytest

from birdbot.workflow.runtime import TransientError, WorkflowRuntime


class FakeClock:
    """Records backoff sleeps and advances virtual time without real waiting."""

    def __init__(self) -> None:
        self.t = 0.0
        self.slept: list[float] = []

    def monotonic(self) -> float:
        return self.t

    async def sleep(self, seconds: float) -> None:
        self.slept.append(seconds)
        self.t += seconds


@pytest.mark.asyncio
async def test_step_executes_and_journals_completed(app_db):
    rt = WorkflowRuntime(app_db)
    calls = []

    async def fn():
        calls.append(1)
        return {"ok": True}

    out = await rt.run_step(tenant_id="A", workflow_id="wf1", step_name="s1", fn=fn)

    assert out == {"ok": True}
    assert calls == [1]
    async with app_db.tenant_scope("A") as conn:
        row = await conn.fetchrow(
            "SELECT status, output FROM workflow_steps "
            "WHERE workflow_id = 'wf1' AND step_name = 's1'"
        )
    assert row["status"] == "completed"
    assert json.loads(row["output"]) == {"ok": True}


@pytest.mark.asyncio
async def test_completed_step_replays_without_reexecuting(app_db):
    """A repeat run of the same step replays the journaled output (idempotent / resume)."""
    rt = WorkflowRuntime(app_db)
    calls = []

    async def fn():
        calls.append(1)
        return {"n": len(calls)}

    out1 = await rt.run_step(tenant_id="A", workflow_id="wf1", step_name="s1", fn=fn)
    out2 = await rt.run_step(tenant_id="A", workflow_id="wf1", step_name="s1", fn=fn)

    assert out1 == out2 == {"n": 1}
    assert calls == [1]  # executed once; second call replayed from the journal


@pytest.mark.asyncio
async def test_retries_transient_failures_then_succeeds(app_db):
    clock = FakeClock()
    rt = WorkflowRuntime(app_db, clock=clock, max_attempts=3)
    attempts = []

    async def fn():
        attempts.append(1)
        if len(attempts) < 3:
            raise TransientError("429")
        return {"ok": True}

    out = await rt.run_step(tenant_id="A", workflow_id="wf-retry", step_name="s1", fn=fn)

    assert out == {"ok": True}
    assert len(attempts) == 3
    assert len(clock.slept) == 2  # backoff between the 3 attempts, no wall-clock wait
    async with app_db.tenant_scope("A") as conn:
        row = await conn.fetchrow(
            "SELECT status, attempts FROM workflow_steps "
            "WHERE workflow_id = 'wf-retry' AND step_name = 's1'"
        )
    assert row["status"] == "completed"
    assert row["attempts"] == 3


@pytest.mark.asyncio
async def test_non_retryable_failure_is_not_retried(app_db):
    clock = FakeClock()
    rt = WorkflowRuntime(app_db, clock=clock, max_attempts=3)
    attempts = []

    async def fn():
        attempts.append(1)
        raise ValueError("bad input")

    with pytest.raises(ValueError):
        await rt.run_step(tenant_id="A", workflow_id="wf-perm", step_name="s1", fn=fn)

    assert attempts == [1]  # permanent failure, not retried
    assert clock.slept == []
    async with app_db.tenant_scope("A") as conn:
        row = await conn.fetchrow(
            "SELECT status FROM workflow_steps "
            "WHERE workflow_id = 'wf-perm' AND step_name = 's1'"
        )
    assert row["status"] == "failed"


@pytest.mark.asyncio
async def test_step_timeout_is_retryable(app_db):
    clock = FakeClock()
    rt = WorkflowRuntime(app_db, clock=clock, max_attempts=2)
    attempts = []

    async def slow():
        attempts.append(1)
        await asyncio.sleep(1.0)  # exceeds the tiny start_to_close timeout

    with pytest.raises(asyncio.TimeoutError):
        await rt.run_step(
            tenant_id="A", workflow_id="wf-to", step_name="s1", fn=slow, timeout=0.02
        )
    assert len(attempts) == 2  # timed out and retried up to max_attempts


@pytest.mark.asyncio
async def test_two_step_workflow_resumes_completed_steps_after_crash(app_db):
    """Two-step noop flow: after a 'crash' between steps, completed steps replay."""
    rt = WorkflowRuntime(app_db)
    s1_runs, s2_runs = [], []

    async def step1():
        s1_runs.append(1)
        return {"a": 1}

    async def step2():
        s2_runs.append(1)
        return {"b": 2}

    # First process: step1 runs, then the process "crashes" before step2.
    await rt.run_step(tenant_id="A", workflow_id="wf-2", step_name="s1", fn=step1)

    # Resume: replay the whole workflow; step1 replays, step2 executes once.
    r1 = await rt.run_step(tenant_id="A", workflow_id="wf-2", step_name="s1", fn=step1)
    r2 = await rt.run_step(tenant_id="A", workflow_id="wf-2", step_name="s2", fn=step2)

    assert r1 == {"a": 1}
    assert r2 == {"b": 2}
    assert s1_runs == [1]  # not re-executed on resume
    assert s2_runs == [1]  # executed once, after resume
