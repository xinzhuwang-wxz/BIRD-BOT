"""WorkflowRuntime — minimal re-entrant step engine (ADR-0002).

run_step journals intent before executing, records the output on success, and on a
second call with the same (workflow_id, step_name) replays the recorded output instead
of re-executing — giving idempotency and crash-resume. Steps run inside a
start_to_close timeout.
"""
from __future__ import annotations

import asyncio
import json
from collections.abc import Awaitable, Callable
from typing import Any

from birdbot.db.pool import Database
from birdbot.workflow.clock import Clock, SystemClock


class TransientError(Exception):
    """A retryable step failure (e.g. 429 / 5xx / timeout). Other exceptions are
    treated as permanent and fail the step without retry."""


# A start_to_close timeout surfaces as asyncio.TimeoutError (== TimeoutError on 3.11);
# treat it, like TransientError, as retryable.
_RETRYABLE: tuple[type[BaseException], ...] = (TransientError, asyncio.TimeoutError)


class WorkflowRuntime:
    def __init__(
        self,
        db: Database,
        *,
        clock: Clock | None = None,
        max_attempts: int = 3,
        base_backoff: float = 0.1,
        max_backoff: float = 5.0,
    ) -> None:
        self._db = db
        self._clock = clock or SystemClock()
        self._max_attempts = max_attempts
        self._base_backoff = base_backoff
        self._max_backoff = max_backoff

    async def run_step(
        self,
        *,
        tenant_id: str,
        workflow_id: str,
        step_name: str,
        fn: Callable[[], Awaitable[Any]],
        timeout: float = 30.0,
    ) -> Any:
        """Execute ``fn`` for ``(workflow_id, step_name)``, or replay its result.

        Retries retryable failures (TransientError / timeout) with exponential backoff
        up to ``max_attempts``; permanent failures fail the step immediately. A step
        already recorded ``completed`` is replayed, never re-executed.
        """
        async with self._db.tenant_scope(tenant_id) as conn:
            row = await conn.fetchrow(
                "SELECT status, output FROM workflow_steps "
                "WHERE workflow_id = $1 AND step_name = $2",
                workflow_id,
                step_name,
            )
            if row is not None and row["status"] == "completed":
                return json.loads(row["output"]) if row["output"] is not None else None
            # Journal intent before executing, so a crash leaves a visible record.
            await conn.execute(
                """
                INSERT INTO workflow_steps (workflow_id, step_name, tenant_id, status)
                VALUES ($1, $2, $3, 'pending')
                ON CONFLICT (workflow_id, step_name) DO NOTHING
                """,
                workflow_id,
                step_name,
                tenant_id,
            )

        for attempt in range(1, self._max_attempts + 1):
            try:
                result = await asyncio.wait_for(fn(), timeout)
            except _RETRYABLE:
                if attempt >= self._max_attempts:
                    await self._record(
                        tenant_id, workflow_id, step_name, "failed", None, attempt
                    )
                    raise
                await self._clock.sleep(
                    min(self._max_backoff, self._base_backoff * (2 ** (attempt - 1)))
                )
            except Exception:
                # Permanent failure: do not retry.
                await self._record(
                    tenant_id, workflow_id, step_name, "failed", None, attempt
                )
                raise
            else:
                await self._record(
                    tenant_id, workflow_id, step_name, "completed", result, attempt
                )
                return result

    async def _record(
        self,
        tenant_id: str,
        workflow_id: str,
        step_name: str,
        status: str,
        output: Any,
        attempts: int,
    ) -> None:
        async with self._db.tenant_scope(tenant_id) as conn:
            await conn.execute(
                """
                UPDATE workflow_steps
                SET status = $4, output = $5::jsonb, attempts = $6, updated_at = now()
                WHERE workflow_id = $1 AND step_name = $2 AND tenant_id = $3
                """,
                workflow_id,
                step_name,
                tenant_id,
                status,
                json.dumps(output) if output is not None else None,
                attempts,
            )
