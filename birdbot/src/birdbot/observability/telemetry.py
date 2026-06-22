"""Structured telemetry for every LLM/tool/external-API call (ADR-0006).

One CallRecord per call captures the full attribution needed for chargeback and
compliance audit: tenant/user/device, logical model -> real provider, fallback chain,
degradation, data-source mode, tokens/cost/latency, and data-flow region.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True, slots=True)
class CallRecord:
    tenant_id: str
    user_id: str | None
    device_id: str | None
    logical_model: str
    provider: str
    fallback_chain: tuple[str, ...]
    degraded: bool
    source_mode: str | None
    tokens: int
    cost_usd: float
    latency_ms: float
    data_flow_region: str | None


class TelemetrySink(Protocol):
    def record(self, call: CallRecord) -> None: ...


class ListTelemetrySink:
    """In-memory sink (MVP). Production fans out to structured logging / a metrics store."""

    def __init__(self) -> None:
        self.records: list[CallRecord] = []

    def record(self, call: CallRecord) -> None:
        self.records.append(call)


def cost_by_tenant(records: list[CallRecord]) -> dict[str, float]:
    """Aggregate spend per tenant for chargeback."""
    totals: dict[str, float] = {}
    for record in records:
        totals[record.tenant_id] = totals.get(record.tenant_id, 0.0) + record.cost_usd
    return totals
