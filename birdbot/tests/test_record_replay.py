"""Unit tests for the record/replay LLM transport (S14).

Lets real end-to-end tests run in CI without a real key/network: record once, replay
forever. A missing recording fails loudly — it never silently hits the network.
"""
from __future__ import annotations

import json

import httpx
import pytest

from birdbot.testing.record_replay import RecordReplayTransport


@pytest.mark.asyncio
async def test_record_then_replay_round_trips(tmp_path):
    cassette = tmp_path / "c.json"
    real = httpx.MockTransport(lambda req: httpx.Response(200, json={"ok": True}))

    rec = RecordReplayTransport(cassette, mode="record", real_transport=real)
    async with httpx.AsyncClient(transport=rec) as client:
        resp = await client.post("https://api.test/v1/chat", json={"a": 1})
        assert resp.json() == {"ok": True}

    # replay needs no real transport and no network
    replay = RecordReplayTransport(cassette, mode="replay")
    async with httpx.AsyncClient(transport=replay) as client:
        resp = await client.post("https://api.test/v1/chat", json={"a": 1})
        assert resp.json() == {"ok": True}


@pytest.mark.asyncio
async def test_replay_missing_recording_fails_loudly(tmp_path):
    replay = RecordReplayTransport(tmp_path / "empty.json", mode="replay")
    async with httpx.AsyncClient(transport=replay) as client:
        with pytest.raises(RuntimeError):
            await client.post("https://api.test/v1/chat", json={"a": 1})


@pytest.mark.asyncio
async def test_record_persists_cassette(tmp_path):
    cassette = tmp_path / "c.json"
    real = httpx.MockTransport(lambda req: httpx.Response(200, json={"v": 42}))
    rec = RecordReplayTransport(cassette, mode="record", real_transport=real)
    async with httpx.AsyncClient(transport=rec) as client:
        await client.post("https://api.test/v1/y", json={"b": 2})

    data = json.loads(cassette.read_text())
    assert any(entry["json"] == {"v": 42} for entry in data.values())


@pytest.mark.asyncio
async def test_replay_distinguishes_requests(tmp_path):
    cassette = tmp_path / "c.json"
    calls = {"n": 0}

    def handler(req):
        calls["n"] += 1
        return httpx.Response(200, json={"call": calls["n"]})

    rec = RecordReplayTransport(cassette, mode="record", real_transport=httpx.MockTransport(handler))
    async with httpx.AsyncClient(transport=rec) as client:
        await client.post("https://api.test/v1/chat", json={"q": "first"})
        await client.post("https://api.test/v1/chat", json={"q": "second"})

    replay = RecordReplayTransport(cassette, mode="replay")
    async with httpx.AsyncClient(transport=replay) as client:
        r1 = await client.post("https://api.test/v1/chat", json={"q": "first"})
        r2 = await client.post("https://api.test/v1/chat", json={"q": "second"})
    assert r1.json() != r2.json()  # distinct bodies -> distinct recordings


@pytest.mark.asyncio
async def test_records_and_replays_a_governed_vision_story_call(tmp_path):
    """End-to-end: a deep-stage vision call recorded once, replayed in CI — and routed
    THROUGH the gateway, so the record/replay path is governed too (ADR-0014). Telemetry is
    recorded on both the record and replay passes."""
    from birdbot.deep.llm import build_story_llm
    from birdbot.observability.alerts import ListAlertSink
    from birdbot.observability.telemetry import ListTelemetrySink
    from birdbot.router.registry import Capability, CapabilityRegistry, ModelEntry
    from birdbot.router.router import ModelRouter
    from birdbot.runtime.completion import openai_sdk_completion
    from birdbot.runtime.gateway import LLMGateway
    from birdbot.tenant.context import TenantEnvelope

    cassette = tmp_path / "llm.json"
    answer = {"behavior": "feeding", "rarity_narrative": "common", "story": "A robin."}
    completion = {
        "id": "x", "object": "chat.completion", "created": 0, "model": "m",
        "choices": [
            {"index": 0, "message": {"role": "assistant", "content": json.dumps(answer)},
             "finish_reason": "stop"}
        ],
        "usage": {"total_tokens": 50},
    }
    real = httpx.MockTransport(lambda req: httpx.Response(200, json=completion))

    router = ModelRouter(CapabilityRegistry([
        ModelEntry(logical_name="deep-reasoning", backend="openai_compat", model="m",
                   capabilities=frozenset({Capability.VISION, Capability.STRUCTURED_OUTPUT}),
                   context_window=128_000, pricing_per_mtok=1.0, residency_region="US",
                   compliance_tags=frozenset({"dpf"}))]))

    class _AllowQuota:
        async def try_acquire(self, key):
            return True

        async def release(self, key):
            pass

    async def story(transport):
        telemetry = ListTelemetrySink()
        gateway = LLMGateway(
            router=router, telemetry=telemetry, alerts=ListAlertSink(), quota=_AllowQuota(),
            completion=openai_sdk_completion(api_key="k", base_url="https://api.test/v1",
                                             transport=transport),
        )
        out = await build_story_llm(gateway=gateway).generate(
            prompt="p", frames=["data:image/jpeg;base64,QQ=="],
            envelope=TenantEnvelope(tenant_id="A", device_id="d1"), region="US",
        )
        return out, telemetry

    recorded, tel_rec = await story(RecordReplayTransport(cassette, mode="record", real_transport=real))
    replayed, tel_rep = await story(RecordReplayTransport(cassette, mode="replay"))
    assert recorded == replayed == answer
    assert len(tel_rec.records) == 1 and len(tel_rep.records) == 1  # governed on both passes
