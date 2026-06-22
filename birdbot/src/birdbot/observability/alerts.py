"""Surfaced alerts (ADR-0006): degradation / circuit-break / quota-exhaustion / source
switch must be surfaced, never silent — and not via logger.warning (the kernel hook
swallows). Components emit to an injected AlertSink with its own delivery."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

# Alert kinds that must never be silent.
DEGRADED = "degraded"
CIRCUIT_BREAK = "circuit_break"
QUOTA_EXHAUSTED = "quota_exhausted"
SOURCE_SWITCH = "source_switch"


@dataclass(frozen=True, slots=True)
class Alert:
    kind: str
    detail: dict[str, Any]


class AlertSink(Protocol):
    def emit(self, alert: Alert) -> None: ...


class ListAlertSink:
    """In-memory sink (MVP). Production routes to a real alerting channel."""

    def __init__(self) -> None:
        self.alerts: list[Alert] = []

    def emit(self, alert: Alert) -> None:
        self.alerts.append(alert)
