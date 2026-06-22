"""ObservabilityHook built ON the kernel AgentHook — must NOT silently swallow (ADR-0006).

The kernel AgentHook defaults to reraise=False (CompositeHook swallows hook errors); the
BirdBot hook flips that so failures surface."""
from __future__ import annotations

import pytest
from nanobot.agent.hook import AgentHookContext, CompositeHook

from birdbot.observability.alerts import Alert, ListAlertSink
from birdbot.observability.hook import ObservabilityHook
from birdbot.observability.telemetry import CallRecord, ListTelemetrySink


def test_hook_is_not_silent_unlike_kernel_default():
    hook = ObservabilityHook(ListTelemetrySink(), ListAlertSink())
    assert hook._reraise is True  # kernel AgentHook default is False (silent)


@pytest.mark.asyncio
async def test_hook_error_propagates_through_composite():
    class Boom(ObservabilityHook):
        async def after_iteration(self, context):
            raise RuntimeError("boom")

    composite = CompositeHook([Boom(ListTelemetrySink(), ListAlertSink())])
    with pytest.raises(RuntimeError):
        await composite.after_iteration(AgentHookContext(iteration=0, messages=[]))


def test_hook_records_telemetry_and_surfaces_alerts():
    tel, al = ListTelemetrySink(), ListAlertSink()
    hook = ObservabilityHook(tel, al)

    hook.record(
        CallRecord("A", None, None, "m", "p", (), True, "auto", 10, 0.01, 5.0, "US")
    )
    hook.surface(Alert("degraded", {"reason": "fallback"}))

    assert tel.records[0].degraded is True
    assert al.alerts[0].kind == "degraded"
