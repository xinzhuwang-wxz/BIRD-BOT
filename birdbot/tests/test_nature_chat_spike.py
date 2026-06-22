"""Spike: does nanobot's agent loop carry the open interaction layer (Nature Chat)?

Drives a real AgentLoop with a scripted fake provider + BirdBot tools through a
multi-turn, autonomous tool-calling exchange — the thing the deterministic main line
never exercises. Verifies the loop orchestrates several tools across turns and weaves the
results into a final answer.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from birdbot.chat.tools import BirdContextTool, DeviceHistoryTool


@pytest.mark.asyncio
async def test_agent_loop_orchestrates_multi_turn_nature_chat(tmp_path):
    from nanobot.agent.loop import AgentLoop
    from nanobot.agent.tools.registry import ToolRegistry
    from nanobot.bus.queue import MessageBus
    from nanobot.providers.base import LLMResponse, ToolCallRequest

    provider = MagicMock()
    provider.get_default_model.return_value = "test-model"
    provider.chat_with_retry = AsyncMock(
        side_effect=[
            LLMResponse(
                content="",
                tool_calls=[ToolCallRequest("c1", "device_history", {"species": "blue tit"})],
                usage={},
            ),
            LLMResponse(
                content="",
                tool_calls=[ToolCallRequest("c2", "bird_context", {"species": "blue tit"})],
                usage={},
            ),
            LLMResponse(
                content="Yes — a regular: 8 visits in the last 30 days, and locally common.",
                tool_calls=[],
                usage={},
            ),
        ]
    )

    loop = AgentLoop(bus=MessageBus(), provider=provider, workspace=tmp_path, model="test-model")
    history = DeviceHistoryTool({"blue tit": {"visits_30d": 8}})
    context = BirdContextTool({"blue tit": "common"}, region="US-CA")
    registry = ToolRegistry()
    registry.register(history)
    registry.register(context)

    result = await loop.process_direct(
        "Is this blue tit a regular at my feeder?",
        tools=registry,
        session_key="tenant:t1:user:u1:device:d1",
    )

    assert result is not None
    assert "regular" in result.content.lower()
    # The agent loop autonomously chose to call BOTH tools, across separate turns:
    assert history.calls == [{"species": "blue tit"}]
    # region was bound deterministically at construction, NOT sent by the LLM:
    assert context.calls == [{"species": "blue tit", "region": "US-CA"}]
    assert provider.chat_with_retry.await_count == 3  # 2 tool turns + final answer
