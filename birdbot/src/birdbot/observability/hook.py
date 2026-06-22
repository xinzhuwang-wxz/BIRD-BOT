"""ObservabilityHook — built ON the kernel AgentHook, with reraise=True.

The kernel AgentHook defaults to reraise=False, so CompositeHook silently swallows hook
errors (the audit finding behind ADR-0006). This hook flips that to surface failures, and
carries the telemetry/alert sinks so the collection/metering path never depends on
logger.warning.
"""
from __future__ import annotations

from nanobot.agent.hook import AgentHook

from birdbot.observability.alerts import Alert, AlertSink
from birdbot.observability.telemetry import CallRecord, TelemetrySink


class ObservabilityHook(AgentHook):
    def __init__(self, telemetry: TelemetrySink, alerts: AlertSink) -> None:
        super().__init__(reraise=True)  # never silent (ADR-0006)
        self._telemetry = telemetry
        self._alerts = alerts

    def record(self, call: CallRecord) -> None:
        self._telemetry.record(call)

    def surface(self, alert: Alert) -> None:
        self._alerts.emit(alert)
