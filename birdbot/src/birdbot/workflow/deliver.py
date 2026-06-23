"""HTTP outbox delivery (ADR-0002): POST each callback to a webhook.

at-least-once; the consumer dedupes by dedupe_key. A non-2xx response raises, so the relay
leaves the row pending for the next sweep instead of marking it delivered.
"""
from __future__ import annotations

from typing import Any


class HttpDeliver:
    """A relay ``deliver`` callable that POSTs the outbox message to a webhook URL."""

    def __init__(self, *, webhook_url: str, client: Any, timeout: float = 10.0) -> None:
        self._url = webhook_url
        self._client = client
        self._timeout = timeout

    async def __call__(self, msg: dict[str, Any]) -> None:
        resp = await self._client.post(self._url, json=msg, timeout=self._timeout)
        resp.raise_for_status()  # non-2xx -> raise -> relay keeps the row pending
