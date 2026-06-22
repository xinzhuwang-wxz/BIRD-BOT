"""Unit tests for the structured-logging telemetry/alert sinks (S17).

Real backend = loguru structured records (production can route loguru to metrics). Alerts
are surfaced via the sink's own channel, never dropped (ADR-0006)."""
from __future__ import annotations

import json

import pytest
from loguru import logger

from birdbot.observability.alerts import Alert
from birdbot.observability.sinks import LoggingAlertSink, LoggingTelemetrySink
from birdbot.observability.telemetry import CallRecord


@pytest.fixture
def captured():
    lines: list[str] = []
    handler_id = logger.add(lines.append, level="INFO", serialize=True)
    try:
        yield lines
    finally:
        logger.remove(handler_id)


def test_telemetry_sink_emits_full_attribution(captured):
    LoggingTelemetrySink().record(
        CallRecord(
            tenant_id="A", user_id="u1", device_id="d1", logical_model="deep-reasoning",
            provider="anthropic", fallback_chain=("anthropic",), degraded=False,
            source_mode="auto", tokens=1200, cost_usd=0.03, latency_ms=850.0,
            data_flow_region="US",
        )
    )
    extra = json.loads(captured[-1])["record"]["extra"]
    assert extra["tenant_id"] == "A"
    assert extra["logical_model"] == "deep-reasoning"
    assert extra["provider"] == "anthropic"
    assert extra["cost_usd"] == 0.03
    assert extra["data_flow_region"] == "US"


def test_alert_sink_surfaces_alert(captured):
    LoggingAlertSink().emit(Alert("quota_exhausted", {"tenant": "A", "key": "story/opus"}))
    extra = json.loads(captured[-1])["record"]["extra"]
    assert extra["event"] == "alert"
    assert extra["kind"] == "quota_exhausted"
    assert extra["tenant"] == "A"
