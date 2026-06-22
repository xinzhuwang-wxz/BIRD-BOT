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
async def test_records_and_replays_an_openai_vision_story_call(tmp_path):
    """End-to-end use: an OpenAICompatStoryLLM vision call recorded once, replayed in CI."""
    from openai import AsyncOpenAI

    from birdbot.deep.llm import OpenAICompatStoryLLM
    from birdbot.deep.story import STORY_SCHEMA

    cassette = tmp_path / "llm.json"
    answer = {"behavior": "feeding", "rarity_narrative": "common", "story": "A robin."}
    completion = {
        "id": "x", "object": "chat.completion", "created": 0, "model": "m",
        "choices": [
            {"index": 0, "message": {"role": "assistant", "content": json.dumps(answer)},
             "finish_reason": "stop"}
        ],
    }
    real = httpx.MockTransport(lambda req: httpx.Response(200, json=completion))

    async def story(transport):
        client = AsyncOpenAI(
            api_key="k", base_url="https://api.test/v1",
            http_client=httpx.AsyncClient(transport=transport),
        )
        return await OpenAICompatStoryLLM(client=client, model="m").generate(
            prompt="p", frames=["data:image/jpeg;base64,QQ=="], schema=STORY_SCHEMA, model="m"
        )

    recorded = await story(RecordReplayTransport(cassette, mode="record", real_transport=real))
    replayed = await story(RecordReplayTransport(cassette, mode="replay"))
    assert recorded == replayed == answer
