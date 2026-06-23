"""① LLMGateway (ADR-0014): governance is by-construction around every LLM round-trip.

A success records a CallRecord; quota-full / provider-failure / routing-error all surface
(alert + telemetry) and raise — never silent. Quota is checked before routing.
"""
from __future__ import annotations

import asyncio

import pytest

from birdbot.observability.alerts import DEGRADED, QUOTA_EXHAUSTED, ListAlertSink
from birdbot.observability.telemetry import ListTelemetrySink
from birdbot.router.registry import Capability, ModelEntry
from birdbot.router.router import RoutingError
from birdbot.runtime.gateway import (
    GatewayResult,
    LLMGateway,
    ProviderCallError,
    QuotaExhaustedError,
)
from birdbot.tenant.context import TenantEnvelope

_ENVELOPE = TenantEnvelope(tenant_id="A", user_id="u1", device_id="d1")
_ENTRY = ModelEntry(
    logical_name="deep-reasoning",
    backend="openai_compat",
    model="glm-4v",
    capabilities=frozenset({Capability.VISION}),
    context_window=128_000,
    pricing_per_mtok=2.0,
    residency_region="US",
    compliance_tags=frozenset({"dpf"}),
)


class _FakeRouter:
    def __init__(self, entry=None, raises=None):
        self._entry, self._raises = entry, raises
        self.calls = 0

    def resolve(self, logical_name, *, required=(), user_region="US"):
        self.calls += 1
        if self._raises:
            raise self._raises
        return self._entry


class _FakeQuota:
    def __init__(self, allow=True):
        self._allow = allow
        self.acquired, self.released = [], []

    async def try_acquire(self, key):
        self.acquired.append(key)
        return self._allow

    async def release(self, key):
        self.released.append(key)


class _FakeCompletion:
    def __init__(self, response=None, raises=None):
        self._response, self._raises = response, raises
        self.calls = 0

    async def __call__(self, *, model, messages, **kw):
        self.calls += 1
        if self._raises:
            raise self._raises
        return self._response


def _clock():
    vals = iter([0.0, 0.05])
    return lambda: next(vals, 0.05)


def _gateway(*, router, quota, completion, telemetry, alerts):
    return LLMGateway(router=router, telemetry=telemetry, alerts=alerts, quota=quota,
                      completion=completion, clock=_clock(), timeout=30.0)


def _ok_completion():
    return _FakeCompletion(response={"choices": [{"message": {"content": "hi"}}],
                                     "usage": {"total_tokens": 100}})


@pytest.mark.asyncio
async def test_success_records_callrecord_and_returns_result():
    tel, al, q = ListTelemetrySink(), ListAlertSink(), _FakeQuota(allow=True)
    gw = _gateway(router=_FakeRouter(_ENTRY), quota=q, completion=_ok_completion(), telemetry=tel, alerts=al)

    result = await gw.complete(envelope=_ENVELOPE, logical_model="deep-reasoning",
                               messages=[{"role": "user", "content": "x"}], skill="deep")

    assert isinstance(result, GatewayResult)
    assert result.provider == "openai_compat" and result.tokens == 100
    assert result.cost_usd == pytest.approx(2.0 * 100 / 1_000_000)  # pricing × tokens
    assert result.latency_ms == pytest.approx(50.0)
    assert not result.degraded
    # telemetry recorded by construction
    rec = tel.records[0]
    assert rec.tenant_id == "A" and rec.logical_model == "deep-reasoning"
    assert rec.provider == "openai_compat" and rec.data_flow_region == "US"
    assert rec.tokens == 100 and rec.degraded is False
    assert al.alerts == []  # no alert on success
    assert q.acquired and q.released  # acquired and released


@pytest.mark.asyncio
async def test_quota_full_surfaces_and_raises_before_routing():
    tel, al, q = ListTelemetrySink(), ListAlertSink(), _FakeQuota(allow=False)
    router, completion = _FakeRouter(_ENTRY), _ok_completion()
    gw = _gateway(router=router, quota=q, completion=completion, telemetry=tel, alerts=al)

    with pytest.raises(QuotaExhaustedError):
        await gw.complete(envelope=_ENVELOPE, logical_model="deep-reasoning",
                          messages=[], skill="deep")

    assert al.alerts[0].kind == QUOTA_EXHAUSTED       # surfaced
    assert router.calls == 0 and completion.calls == 0  # never routed / called
    assert q.released == []                            # nothing to release (acquire failed)


@pytest.mark.asyncio
async def test_provider_failure_classifies_alerts_records_degraded_and_raises():
    tel, al, q = ListTelemetrySink(), ListAlertSink(), _FakeQuota(allow=True)
    boom = _FakeCompletion(raises=RuntimeError("503 service unavailable"))
    gw = _gateway(router=_FakeRouter(_ENTRY), quota=q, completion=boom, telemetry=tel, alerts=al)

    with pytest.raises(ProviderCallError) as ei:
        await gw.complete(envelope=_ENVELOPE, logical_model="deep-reasoning",
                          messages=[], skill="deep")

    assert ei.value.failure_class.value == "generic"
    assert al.alerts[0].kind == DEGRADED
    assert tel.records[0].degraded is True            # degraded telemetry recorded
    assert q.released                                  # released in finally


@pytest.mark.asyncio
async def test_routing_error_fails_fast_not_as_provider_error():
    tel, al, q = ListTelemetrySink(), ListAlertSink(), _FakeQuota(allow=True)
    gw = _gateway(router=_FakeRouter(raises=RoutingError("no eligible entry")),
                  quota=q, completion=_ok_completion(), telemetry=tel, alerts=al)

    with pytest.raises(RoutingError):  # propagates, NOT wrapped as ProviderCallError
        await gw.complete(envelope=_ENVELOPE, logical_model="deep-reasoning",
                          messages=[], skill="deep")

    assert q.released  # released in finally


@pytest.mark.asyncio
async def test_timeout_becomes_provider_call_error():
    tel, al, q = ListTelemetrySink(), ListAlertSink(), _FakeQuota(allow=True)
    timeout = _FakeCompletion(raises=asyncio.TimeoutError())
    gw = _gateway(router=_FakeRouter(_ENTRY), quota=q, completion=timeout, telemetry=tel, alerts=al)

    with pytest.raises(ProviderCallError):
        await gw.complete(envelope=_ENVELOPE, logical_model="deep-reasoning",
                          messages=[], skill="deep")
    assert tel.records[0].degraded is True
