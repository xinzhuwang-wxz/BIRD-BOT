"""Unit tests for the real StoryLLM (OpenAI-compatible, vision) and its Model Router wiring.

Uses httpx MockTransport (real OpenAI SDK, mocked HTTP) — no live LLM. Verifies the deep
stage sends curated frames as vision image parts, parses the JSON answer, and that the
model is chosen by the Model Router (logical -> real)."""
from __future__ import annotations

import json

import httpx
import pytest
from openai import AsyncOpenAI

from birdbot.deep.llm import OpenAICompatStoryLLM, build_story_llm
from birdbot.deep.story import STORY_SCHEMA
from birdbot.router.registry import Capability, CapabilityRegistry, ModelEntry
from birdbot.router.router import ModelRouter

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


def test_build_story_llm_routes_model_via_router():
    registry = CapabilityRegistry(
        [
            ModelEntry(
                logical_name="deep-reasoning",
                backend="openai_compat",
                model="glm-4v",
                capabilities=frozenset({Capability.VISION, Capability.STRUCTURED_OUTPUT}),
                context_window=128_000,
                pricing_per_mtok=2.0,
                residency_region="US",
                compliance_tags=frozenset({"dpf"}),
            )
        ]
    )
    client = AsyncOpenAI(api_key="test", base_url="https://api.test/v1")
    llm = build_story_llm(router=ModelRouter(registry), client=client, user_region="US")
    assert llm.model == "glm-4v"  # logical "deep-reasoning" -> real model
