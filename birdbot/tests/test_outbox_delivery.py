"""③ (ADR-0002): HTTP outbox delivery + relay worker loop. No DB — sweep/client injected."""
from __future__ import annotations

import pytest

from birdbot.workflow.deliver import HttpDeliver
from birdbot.workflow.worker import RelayWorker


class _FakeResp:
    def __init__(self, status: int) -> None:
        self._status = status

    def raise_for_status(self) -> None:
        if self._status >= 400:
            raise RuntimeError(f"HTTP {self._status}")


class _FakeClient:
    def __init__(self, status: int = 200) -> None:
        self._status = status
        self.posts: list[dict] = []

    async def post(self, url, *, json, timeout):
        self.posts.append({"url": url, "json": json, "timeout": timeout})
        return _FakeResp(self._status)


@pytest.mark.asyncio
async def test_http_deliver_posts_callback_to_webhook():
    client = _FakeClient(200)
    deliver = HttpDeliver(webhook_url="https://hook/cb", client=client)

    await deliver({"tenant_id": "A", "topic": "callback", "payload": {"x": 1}})

    assert client.posts[0]["url"] == "https://hook/cb"
    assert client.posts[0]["json"]["tenant_id"] == "A"


@pytest.mark.asyncio
async def test_http_deliver_raises_on_non_2xx_so_relay_keeps_pending():
    deliver = HttpDeliver(webhook_url="https://hook/cb", client=_FakeClient(500))
    with pytest.raises(RuntimeError):
        await deliver({"tenant_id": "A"})  # relay catches this -> row stays pending


@pytest.mark.asyncio
async def test_relay_worker_sweeps_then_sleeps_until_stopped():
    calls = {"sweeps": 0}

    async def sweep() -> int:
        calls["sweeps"] += 1
        return 1

    worker = RelayWorker(sweep=sweep, interval=1.0)

    async def fake_sleep(_seconds):
        worker._running = False  # stop after the first interval

    worker._sleep = fake_sleep
    await worker.start()
    assert worker._task is not None
    await worker._task

    assert calls["sweeps"] == 1  # one sweep ran before the loop stopped


class _FakeConn:
    def __init__(self, rows):
        self._rows = rows

    async def fetch(self, query, *args):
        return self._rows

    async def close(self):
        pass


@pytest.mark.asyncio
async def test_deep_sweep_drives_queued_events_with_region_from_location():
    import json

    from birdbot.workflow.worker import make_deep_sweep

    rows = [
        {"tenant_id": "A", "device_id": "d1", "event_id": "e1",
         "payload": json.dumps({"fast_stage": {}, "location": {"region": "US-CA"}})},
        {"tenant_id": "B", "device_id": "d2", "event_id": "e2",
         "payload": json.dumps({"fast_stage": {}})},  # no location -> default region
    ]
    driven = []

    async def advance(*, tenant_id, device_id, event_id, region):
        driven.append({"event": event_id, "region": region})

    async def connect(_dsn):
        return _FakeConn(rows)

    sweep = make_deep_sweep(owner_dsn="x", advance=advance, connect=connect)
    assert await sweep() == 2
    assert driven[0]["region"] == "US-CA"  # IoT-supplied region code
    assert driven[1]["region"] == "US"  # default when no location supplied


@pytest.mark.asyncio
async def test_deep_sweep_skips_failed_event_keeps_going():
    import json

    from birdbot.workflow.worker import make_deep_sweep

    rows = [
        {"tenant_id": "A", "device_id": "d1", "event_id": "bad",
         "payload": json.dumps({"fast_stage": {}, "location": {"region": "US"}})},
        {"tenant_id": "A", "device_id": "d1", "event_id": "good",
         "payload": json.dumps({"fast_stage": {}, "location": {"region": "US"}})},
    ]
    driven = []

    async def advance(*, tenant_id, device_id, event_id, region):
        if event_id == "bad":
            raise RuntimeError("boom")  # leaves it queued for next sweep
        driven.append(event_id)

    async def connect(_dsn):
        return _FakeConn(rows)

    sweep = make_deep_sweep(owner_dsn="x", advance=advance, connect=connect)
    assert await sweep() == 1  # only "good" driven; "bad" skipped (idempotent retry next sweep)
    assert driven == ["good"]
