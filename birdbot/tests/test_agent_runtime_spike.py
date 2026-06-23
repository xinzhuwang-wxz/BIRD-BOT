"""② AgentRuntime (ADR-0014): open-layer agent loop over the governed LLMGateway.

Drives multi-turn autonomous tool calls; tool failures (hallucinated name / execute raising)
are fed back to the model as error observations (not crashes); a gateway failure or
max-iterations exhaustion degrades to a human line + surfaces an alert — never silent.
"""
from __future__ import annotations

import json

import pytest

from birdbot.chat.tools import BirdContextTool, DeviceHistoryTool
from birdbot.observability.alerts import DEGRADED, ListAlertSink
from birdbot.router.validate import FailureClass
from birdbot.runtime.agent import AgentRuntime
from birdbot.runtime.gateway import GatewayResult, ProviderCallError
from birdbot.tenant.context import TenantEnvelope

_ENV = TenantEnvelope(tenant_id="t1", user_id="u1", device_id="d1")


def _msg(content="", tool_calls=None):
    return {"choices": [{"message": {"content": content, "tool_calls": tool_calls}}]}


def _tc(call_id, name, args):
    return {"id": call_id, "type": "function",
            "function": {"name": name, "arguments": json.dumps(args)}}


class FakeGateway:
    """Mimics LLMGateway.complete(...) -> GatewayResult; scripts responses or raises."""

    def __init__(self, responses, raises=None):
        self._responses = responses
        self._raises = raises
        self.calls = 0
        self.seen: list[dict] = []

    async def complete(self, *, envelope, logical_model, messages, skill, region="US", **kw):
        self.seen.append({"messages": [dict(m) for m in messages], "skill": skill,
                          "region": region, "kw": kw})
        if self._raises:
            raise self._raises
        resp = self._responses[min(self.calls, len(self._responses) - 1)]
        self.calls += 1
        return GatewayResult(raw=resp, provider="x", tokens=1, cost_usd=0.0, latency_ms=1.0)


@pytest.mark.asyncio
async def test_runtime_drives_multi_turn_autonomous_tools():
    gw = FakeGateway([
        _msg(tool_calls=[_tc("c1", "device_history", {"species": "blue tit"})]),
        _msg(tool_calls=[_tc("c2", "bird_context", {"species": "blue tit"})]),
        _msg(content="Yes — a regular: 8 visits in 30 days, and locally common."),
    ])
    runtime = AgentRuntime(gateway=gw, alerts=ListAlertSink())
    history = DeviceHistoryTool({"blue tit": {"visits_30d": 8}}, device_id="d1")
    context = BirdContextTool({"blue tit": "common"}, region="US-CA")

    answer = await runtime.run(prompt="Is this blue tit a regular?",
                               tools=[history, context], envelope=_ENV, region="US-CA")

    assert "regular" in answer.lower()
    assert history.calls == [{"species": "blue tit", "device_id": "d1"}]
    assert context.calls[-1]["region"] == "US-CA"  # deterministic region (S13) preserved
    assert gw.calls == 3
    # governed call carried skill + region; tools advertised as function schemas
    assert gw.seen[0]["skill"] == "chat" and gw.seen[0]["region"] == "US-CA"
    assert {t["function"]["name"] for t in gw.seen[0]["kw"]["tools"]} == {"device_history", "bird_context"}


@pytest.mark.asyncio
async def test_runtime_returns_on_no_tool_calls():
    gw = FakeGateway([_msg(content="Just a hello.")])
    runtime = AgentRuntime(gateway=gw, alerts=ListAlertSink())
    assert await runtime.run(prompt="hi", tools=[], envelope=_ENV) == "Just a hello."


@pytest.mark.asyncio
async def test_runtime_degrades_and_alerts_on_max_iterations():
    looping = FakeGateway([_msg(tool_calls=[_tc("c", "device_history", {"species": "x"})])])
    alerts = ListAlertSink()
    runtime = AgentRuntime(gateway=looping, alerts=alerts, max_iterations=3)
    history = DeviceHistoryTool({}, device_id="d1")

    out = await runtime.run(prompt="loop", tools=[history], envelope=_ENV)

    assert looping.calls == 3
    assert out == runtime._degraded  # NOT a silent empty string
    assert alerts.alerts[-1].kind == DEGRADED
    assert alerts.alerts[-1].detail["reason"] == "max_iterations"


@pytest.mark.asyncio
async def test_runtime_feeds_unknown_tool_error_back_to_model():
    gw = FakeGateway([
        _msg(tool_calls=[_tc("c1", "nonexistent_tool", {})]),
        _msg(content="ok, recovered"),
    ])
    alerts = ListAlertSink()
    runtime = AgentRuntime(gateway=gw, alerts=alerts)

    out = await runtime.run(prompt="x", tools=[], envelope=_ENV)

    assert out == "ok, recovered"  # recovered instead of crashing
    tool_msgs = [m for m in gw.seen[1]["messages"] if m.get("role") == "tool"]
    assert "unknown tool" in tool_msgs[0]["content"]  # error observation fed back
    assert alerts.alerts[-1].detail["reason"] == "unknown_tool"


@pytest.mark.asyncio
async def test_runtime_feeds_execute_failure_back_to_model():
    class _BoomTool:
        name = "boom"
        description = "always fails"
        parameters = {"type": "object", "properties": {}}

        async def execute(self, **kwargs):
            raise RuntimeError("kaboom")

    gw = FakeGateway([
        _msg(tool_calls=[_tc("c1", "boom", {})]),
        _msg(content="handled"),
    ])
    alerts = ListAlertSink()
    runtime = AgentRuntime(gateway=gw, alerts=alerts)

    out = await runtime.run(prompt="x", tools=[_BoomTool()], envelope=_ENV)

    assert out == "handled"
    tool_msgs = [m for m in gw.seen[1]["messages"] if m.get("role") == "tool"]
    assert "failed" in tool_msgs[0]["content"]
    assert alerts.alerts[-1].detail["reason"] == "tool_failed"


@pytest.mark.asyncio
async def test_runtime_degrades_on_gateway_failure():
    gw = FakeGateway([], raises=ProviderCallError("503", failure_class=FailureClass.GENERIC))
    runtime = AgentRuntime(gateway=gw, alerts=ListAlertSink())

    out = await runtime.run(prompt="x", tools=[], envelope=_ENV)

    assert out == runtime._degraded  # human line; the gateway already surfaced the alert
