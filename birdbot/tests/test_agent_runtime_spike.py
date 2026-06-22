"""Spike (ADR-0013): can a self-built thin AgentRuntime replace nanobot's AgentLoop?

Drives a multi-turn, autonomous tool-calling exchange with a scripted fake completion
(mimics litellm.acompletion) — same shape #9 proved on nanobot, now on our own loop. If
this holds (and the live smoke confirms decision quality), nanobot can be removed.
"""
from __future__ import annotations

import json

import pytest

from birdbot.chat.tools import BirdContextTool, DeviceHistoryTool
from birdbot.runtime.agent import AgentRuntime


def _msg(content="", tool_calls=None):
    return {"choices": [{"message": {"content": content, "tool_calls": tool_calls}}]}


def _tc(call_id, name, args):
    return {"id": call_id, "type": "function",
            "function": {"name": name, "arguments": json.dumps(args)}}


class FakeCompletion:
    """Mimics litellm.acompletion(model=, messages=, tools=) -> dict."""

    def __init__(self, responses):
        self._responses = responses
        self.calls = 0
        self.seen_tools = None

    async def __call__(self, *, model, messages, tools):
        self.seen_tools = tools
        resp = self._responses[self.calls]
        self.calls += 1
        return resp


@pytest.mark.asyncio
async def test_runtime_drives_multi_turn_autonomous_tools():
    completion = FakeCompletion([
        _msg(tool_calls=[_tc("c1", "device_history", {"species": "blue tit"})]),
        _msg(tool_calls=[_tc("c2", "bird_context", {"species": "blue tit"})]),
        _msg(content="Yes — a regular: 8 visits in 30 days, and locally common."),
    ])
    runtime = AgentRuntime(model="doubao-seed-2-0-pro", completion=completion)
    history = DeviceHistoryTool({"blue tit": {"visits_30d": 8}}, device_id="d1")
    context = BirdContextTool({"blue tit": "common"}, region="US-CA")

    answer = await runtime.run(
        prompt="Is this blue tit a regular at my feeder?", tools=[history, context]
    )

    assert "regular" in answer.lower()
    # the loop autonomously called both tools across turns
    assert history.calls == [{"species": "blue tit", "device_id": "d1"}]
    assert context.calls[-1]["region"] == "US-CA"  # deterministic region (S13) preserved
    assert completion.calls == 3  # 2 tool turns + final
    # tools were advertised to the model as function schemas
    assert {t["function"]["name"] for t in completion.seen_tools} == {"device_history", "bird_context"}


@pytest.mark.asyncio
async def test_runtime_returns_on_no_tool_calls():
    completion = FakeCompletion([_msg(content="Just a hello.")])
    runtime = AgentRuntime(model="m", completion=completion)
    assert await runtime.run(prompt="hi", tools=[]) == "Just a hello."


@pytest.mark.asyncio
async def test_runtime_stops_at_max_iterations():
    # always returns a tool call -> must stop at max_iterations, not loop forever
    looping = FakeCompletion([_msg(tool_calls=[_tc("c", "device_history", {"species": "x"})])] * 10)
    runtime = AgentRuntime(model="m", completion=looping, max_iterations=3)
    history = DeviceHistoryTool({}, device_id="d1")
    await runtime.run(prompt="loop", tools=[history])
    assert looping.calls == 3
