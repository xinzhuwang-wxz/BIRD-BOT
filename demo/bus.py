"""A tiny async pub/sub used to stream live pipeline / telemetry / alert events to the
browser over Server-Sent Events. Each subscriber gets its own bounded queue; a slow
subscriber drops oldest rather than backing up producers."""
from __future__ import annotations

import asyncio
from collections import deque
from collections.abc import AsyncIterator


class Broadcaster:
    def __init__(self, *, replay: int = 50, max_queue: int = 200) -> None:
        self._subs: set[asyncio.Queue[dict]] = set()
        self._recent: deque[dict] = deque(maxlen=replay)
        self._max_queue = max_queue

    def publish(self, event: dict) -> None:
        self._recent.append(event)
        for q in list(self._subs):
            if q.qsize() >= self._max_queue:
                try:
                    q.get_nowait()  # drop oldest for slow consumers
                except asyncio.QueueEmpty:
                    pass
            q.put_nowait(event)

    async def subscribe(self) -> AsyncIterator[dict]:
        q: asyncio.Queue[dict] = asyncio.Queue()
        for event in list(self._recent):  # replay recent history to a fresh tab
            q.put_nowait(event)
        self._subs.add(q)
        try:
            while True:
                yield await q.get()
        finally:
            self._subs.discard(q)
