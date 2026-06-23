"""Unit tests for the deep-stage StoryLLM (GatewayStoryLLM, ADR-0014).

The adapter builds curated frames as vision image parts, routes the call through the
LLMGateway (which resolves the model + governs the call), and parses the JSON answer
(json-repair tolerant). The OpenAI-SDK record/replay path is covered by test_record_replay.
"""
from __future__ import annotations

import json

import pytest

from birdbot.deep.llm import GatewayStoryLLM, build_story_llm
from birdbot.runtime.gateway import GatewayResult
from birdbot.tenant.context import TenantEnvelope

_ANSWER = {"behavior": "feeding", "rarity_narrative": "common locally", "story": "A robin fed."}


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
