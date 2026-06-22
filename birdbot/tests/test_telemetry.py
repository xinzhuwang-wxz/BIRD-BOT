"""Unit tests for structured telemetry (full attribution + chargeback) and surfaced
alerts (pure). ADR-0006: record every call's dimensions; never swallow degradation."""
from __future__ import annotations

import pytest

from birdbot.observability.alerts import Alert, ListAlertSink
from birdbot.observability.telemetry import CallRecord, ListTelemetrySink, cost_by_tenant


def _rec(tenant, cost, **kw):
    base = dict(
        tenant_id=tenant, user_id=None, device_id=None, logical_model="m", provider="p",
        fallback_chain=(), degraded=False, source_mode=None, tokens=0, cost_usd=cost,
        latency_ms=0.0, data_flow_region=None,
    )
    base.update(kw)
    return CallRecord(**base)


def test_records_full_attribution():
    sink = ListTelemetrySink()
    sink.record(
        CallRecord(
            tenant_id="A", user_id="u1", device_id="d1", logical_model="deep-reasoning",
            provider="anthropic", fallback_chain=("anthropic",), degraded=False,
            source_mode="auto", tokens=1200, cost_usd=0.03, latency_ms=850.0,
            data_flow_region="US",
        )
    )
    r = sink.records[0]
    assert (r.tenant_id, r.logical_model, r.provider) == ("A", "deep-reasoning", "anthropic")
    assert (r.tokens, r.cost_usd, r.data_flow_region) == (1200, 0.03, "US")


def test_cost_by_tenant_aggregates_for_chargeback():
    sink = ListTelemetrySink()
    for tenant, cost in [("A", 0.03), ("A", 0.02), ("B", 0.10)]:
        sink.record(_rec(tenant, cost))
    assert cost_by_tenant(sink.records) == {"A": pytest.approx(0.05), "B": pytest.approx(0.10)}


def test_alert_sink_surfaces_degradation():
    alerts = ListAlertSink()
    alerts.emit(Alert("quota_exhausted", {"tenant": "A", "key": "story/opus"}))
    assert alerts.alerts[0].kind == "quota_exhausted"
    assert alerts.alerts[0].detail["tenant"] == "A"
