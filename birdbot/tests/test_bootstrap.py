"""③ (ADR-0014): composition root wires a governed, deployable app from components."""
from __future__ import annotations

import pytest

from birdbot.bootstrap import Assembly, assemble
from birdbot.deep.llm import GatewayStoryLLM
from birdbot.observability.alerts import ListAlertSink
from birdbot.observability.telemetry import ListTelemetrySink
from birdbot.router.registry import Capability, CapabilityRegistry, ModelEntry


class _AllowQuota:
    async def try_acquire(self, key):
        return True

    async def release(self, key):
        pass


async def _completion(*, model, messages, **kw):
    return {"choices": [{"message": {"content": "{}"}}], "usage": {"total_tokens": 1}}


def _registry():
    return CapabilityRegistry([
        ModelEntry(logical_name="deep-reasoning", backend="openai_compat", model="m",
                   capabilities=frozenset({Capability.VISION, Capability.STRUCTURED_OUTPUT}),
                   context_window=128_000, pricing_per_mtok=1.0, residency_region="US",
                   compliance_tags=frozenset({"dpf"}))
    ])


def test_assemble_wires_a_governed_deployable_app():
    asm = assemble(
        db=object(),  # EventStore just holds it until a request arrives
        owner_dsn="postgresql://owner@localhost/db",
        registry=_registry(),
        completion=_completion,
        telemetry=ListTelemetrySink(),
        alerts=ListAlertSink(),
        quota=_AllowQuota(),
        webhook_url="https://hook/callbacks",
        http_client=object(),
    )

    assert isinstance(asm, Assembly)
    assert asm.app is not None  # FastAPI ingress assembled
    assert isinstance(asm.story_llm, GatewayStoryLLM)  # deep stage runs on the gateway
    assert callable(asm.advance)  # async deep-stage entry bound to db/runtime/outbox/story_llm
    assert asm.relay_worker is not None  # callback delivery worker ready to start
    assert asm.deep_worker is not None  # fast->deep auto-trigger worker ready to start
    assert asm.chat is not None  # Nature Chat handler mounted at /v0/chat


@pytest.mark.asyncio
async def test_assembled_relay_worker_runs_its_sweep():
    # the assembled worker's sweep is wired; swap it for a probe and confirm the loop drives it
    asm = assemble(
        db=object(), owner_dsn="postgresql://owner@localhost/db", registry=_registry(),
        completion=_completion, telemetry=ListTelemetrySink(), alerts=ListAlertSink(),
        quota=_AllowQuota(), webhook_url="https://hook", http_client=object(),
    )
    swept = {"n": 0}

    async def probe_sweep() -> int:
        swept["n"] += 1
        return 0

    asm.relay_worker._sweep = probe_sweep

    async def fake_sleep(_seconds):
        asm.relay_worker._running = False

    asm.relay_worker._sleep = fake_sleep
    await asm.relay_worker.start()
    await asm.relay_worker._task

    assert swept["n"] == 1
