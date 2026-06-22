"""Structured-logging telemetry/alert sinks (S17, ADR-0006).

Real backend = loguru structured records (serialize=True → JSON; production routes loguru
to a metrics/log store). Same interface as the in-memory sinks (#11), injectable. Alerts
go through this sink's own channel — surfaced, never dropped, not dependent on the kernel
hook's swallowing logger.warning.
"""
from __future__ import annotations

from loguru import logger

from birdbot.observability.alerts import Alert
from birdbot.observability.telemetry import CallRecord


class LoggingTelemetrySink:
    def record(self, call: CallRecord) -> None:
        logger.bind(
            event="llm_call",
            tenant_id=call.tenant_id,
            user_id=call.user_id,
            device_id=call.device_id,
            logical_model=call.logical_model,
            provider=call.provider,
            fallback_chain=list(call.fallback_chain),
            degraded=call.degraded,
            source_mode=call.source_mode,
            tokens=call.tokens,
            cost_usd=call.cost_usd,
            latency_ms=call.latency_ms,
            data_flow_region=call.data_flow_region,
        ).info("llm_call")


class LoggingAlertSink:
    def emit(self, alert: Alert) -> None:
        logger.bind(event="alert", kind=alert.kind, **alert.detail).warning(
            f"alert: {alert.kind}"
        )
