"""Unit tests for the real StoryLLM (OpenAI-compatible, vision) and its Model Router wiring.

Uses httpx MockTransport (real OpenAI SDK, mocked HTTP) — no live LLM. Verifies the deep
stage sends curated frames as vision image parts, parses the JSON answer, and that the
model is chosen by the Model Router (logical -> real)."""
from __future__ import annotations

import json

import httpx
import pytest
from openai import AsyncOpenAI

from birdbot.deep.llm import GatewayStoryLLM, OpenAICompatStoryLLM, build_story_llm
from birdbot.deep.story import STORY_SCHEMA
from birdbot.runtime.gateway import GatewayResult
from birdbot.tenant.context import TenantEnvelope

_ANSWER = {"behavior": "feeding", "rarity_narrative": "common locally", "story": "A robin fed."}


def _completion_json(content: str) -> dict:
    return {
        "id": "x",
        "object": "chat.completion",
        "created": 0,
        "model": "m",
        "choices": [
            {"index": 0, "message": {"role": "assistant", "content": content}, "finish_reason": "stop"}
        ],
    }


@pytest.mark.asyncio
async def test_story_llm_sends_frames_as_vision_and_parses_json():
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(request.content)
        return httpx.Response(200, json=_completion_json(json.dumps(_ANSWER)))

    client = AsyncOpenAI(
        api_key="test",
        base_url="https://api.test/v1",
        http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )
    llm = OpenAICompatStoryLLM(client=client, model="deep-vision")

    out = await llm.generate(
        prompt="describe",
        frames=["data:image/jpeg;base64,QQ=="],
        schema=STORY_SCHEMA,
        model="deep-vision",
    )

    assert out == _ANSWER
    parts = captured["body"]["messages"][0]["content"]
    assert any(p.get("type") == "image_url" for p in parts)  # frame sent as vision
    assert any(p.get("type") == "text" for p in parts)
    assert captured["body"]["model"] == "deep-vision"


@pytest.mark.asyncio
async def test_story_llm_repairs_imperfect_json():
    def handler(request: httpx.Request) -> httpx.Response:
        # trailing prose around the JSON — should still parse
        messy = json.dumps(_ANSWER) + "\n\nHope that helps!"
        return httpx.Response(200, json=_completion_json(messy))

    client = AsyncOpenAI(
        api_key="test",
        base_url="https://api.test/v1",
        http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )
    llm = OpenAICompatStoryLLM(client=client, model="m")
    out = await llm.generate(prompt="p", frames=[], schema=STORY_SCHEMA, model="m")
    assert out["behavior"] == "feeding"


class _FakeGateway:
    """Mimics LLMGateway.complete(...) -> GatewayResult; captures the governed call."""

    def __init__(self, content: str) -> None:
        self._content = content
        self.seen: dict = {}

    async def complete(self, *, envelope, logical_model, messages, skill,
                        required_caps=(), region="US", **kwargs):
        self.seen = {"envelope": envelope, "logical_model": logical_model,
                     "messages": messages, "skill": skill, "region": region, "kwargs": kwargs}
        return GatewayResult(raw={"choices": [{"message": {"content": self._content}}]},
                             provider="openai_compat", tokens=10, cost_usd=0.0, latency_ms=1.0)


@pytest.mark.asyncio
async def test_gateway_story_llm_sends_vision_through_gateway_and_parses_json():
    gw = _FakeGateway(json.dumps(_ANSWER))
    llm = GatewayStoryLLM(gateway=gw)

    out = await llm.generate(
        prompt="describe",
        frames=["data:image/jpeg;base64,QQ=="],
        envelope=TenantEnvelope(tenant_id="A", device_id="d1"),
        region="US-CA",
    )

    assert out == _ANSWER
    parts = gw.seen["messages"][0]["content"]
    assert any(p.get("type") == "image_url" for p in parts)  # frame sent as vision
    assert any(p.get("type") == "text" for p in parts)
    assert gw.seen["logical_model"] == "deep-reasoning"  # gateway resolves the real model
    assert gw.seen["skill"] == "deep"
    assert gw.seen["region"] == "US-CA"  # deterministic region flows to routing
    assert gw.seen["kwargs"]["response_format"] == {"type": "json_object"}


@pytest.mark.asyncio
async def test_gateway_story_llm_repairs_imperfect_json():
    gw = _FakeGateway(json.dumps(_ANSWER) + "\n\nHope that helps!")
    llm = GatewayStoryLLM(gateway=gw)
    out = await llm.generate(prompt="p", frames=[],
                             envelope=TenantEnvelope(tenant_id="A", device_id="d1"))
    assert out["behavior"] == "feeding"


def test_build_story_llm_binds_gateway():
    llm = build_story_llm(gateway=_FakeGateway("{}"))
    assert isinstance(llm, GatewayStoryLLM)  # production deep-stage adapter on the gateway
