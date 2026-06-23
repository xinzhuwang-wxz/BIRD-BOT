"""Outbox relay worker (ADR-0002): periodically sweep + deliver pending outbox rows.

The sweep runs on an owner connection that bypasses RLS, so it covers every tenant. One
sweep delivers up to ``limit`` rows; a failed delivery stays pending for the next sweep
(at-least-once). ``sweep`` is injected so the loop is testable without a DB; ``sleep`` is
injectable for deterministic tests.
"""
from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import Any

import asyncpg

from birdbot.workflow.outbox import relay


def make_outbox_sweep(
    *,
    owner_dsn: str,
    deliver: Callable[[dict[str, Any]], Awaitable[None]],
    limit: int = 100,
    connect: Callable[..., Awaitable[Any]] = asyncpg.connect,
) -> Callable[[], Awaitable[int]]:
    """Build a sweep that opens an owner connection and relays pending rows once."""

    async def sweep() -> int:
        conn = await connect(owner_dsn)
        try:
            return await relay(conn, deliver, limit=limit)
        finally:
            await conn.close()

    return sweep


class RelayWorker:
    """Runs an outbox ``sweep`` on an interval until stopped."""

    def __init__(
        self,
        *,
        sweep: Callable[[], Awaitable[int]],
        interval: float = 5.0,
        sleep: Callable[[float], Awaitable[None]] | None = None,
    ) -> None:
        self._sweep = sweep
        self._interval = interval
        self._sleep = sleep or asyncio.sleep
        self._running = False
        self._task: asyncio.Task[Any] | None = None

    async def start(self) -> None:
        self._running = True
        self._task = asyncio.create_task(self._run())

    async def _run(self) -> None:
        while self._running:
            await self._sweep()
            await self._sleep(self._interval)

    async def stop(self) -> None:
        self._running = False
        if self._task is not None:
            self._task.cancel()
            self._task = None
