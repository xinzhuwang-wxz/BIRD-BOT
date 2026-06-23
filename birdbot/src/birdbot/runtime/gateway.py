"""LLMGateway (ADR-0014): the single governed exit for every LLM round-trip.

completion-level. Wires quota -> route -> time -> completion -> cost -> telemetry around one
LLM call so ADR-0006 (observability) / ADR-0004 (quota) hold *by construction* — nothing can
reach a provider without going through here. Fail-by-raise, never silent. No built-in
fallback (sweeping the router chain is an outer decorator). ``completion`` is an injected
protocol so litellm and the record/replay OpenAI-SDK adapter both run through governance.

Cost is derived from the routed entry's pricing (``pricing_per_mtok``) × tokens — no
dependency on litellm internals, and deterministically testable.
"""
from __future__ import annotations

import asyncio
import time as _time
from collections.abc import Awaitable, Callable, Collection
from dataclasses import dataclass
from typing import Any

from birdbot.observability.alerts import DEGRADED, QUOTA_EXHAUSTED, Alert
from birdbot.observability.quota import QuotaKey
from birdbot.observability.telemetry import CallRecord
from birdbot.router.validate import classify_failure
from birdbot.tenant.context import TenantEnvelope


class QuotaExhaustedError(Exception):
    """The (tenant, skill, model) quota bucket is full — surfaced, never silent."""


class ProviderCallError(Exception):
    """A provider call failed (incl. timeout). Carries the classified failure."""

    def __init__(self, message: str, *, failure_class: Any) -> None:
        super().__init__(message)
        self.failure_class = failure_class


@dataclass(frozen=True, slots=True)
class GatewayResult:
    raw: Any
    provider: str
    tokens: int
    cost_usd: float
    latency_ms: float
    degraded: bool = False


def _default_completion() -> Callable[..., Awaitable[Any]]:
    import litellm

    return litellm.acompletion


class LLMGateway:
    def __init__(
        self,
        *,
        router: Any,
        telemetry: Any,
        alerts: Any,
        quota: Any,
        completion: Callable[..., Awaitable[Any]] | None = None,
        clock: Callable[[], float] | None = None,
        timeout: float = 30.0,
    ) -> None:
        self._router = router
        self._telemetry = telemetry
        self._alerts = alerts
        self._quota = quota
        self._completion = completion or _default_completion()
        self._clock = clock or _time.monotonic
        self._timeout = timeout

    async def complete(
        self,
        *,
        envelope: TenantEnvelope,
        logical_model: str,
        messages: list[dict[str, Any]],
        skill: str,
        required_caps: Collection[Any] = (),
        region: str = "US",
        **provider_kw: Any,
    ) -> GatewayResult:
        key = QuotaKey(envelope.tenant_id, skill, logical_model)

        if not await self._quota.try_acquire(key):
            self._alerts.emit(
                Alert(QUOTA_EXHAUSTED, {"tenant": envelope.tenant_id, "skill": skill, "model": logical_model})
            )
            raise QuotaExhaustedError(f"quota exhausted for {key}")

        try:
            # router.resolve may raise (RoutingError / UnimplementedBackend) -> fail-fast.
            entry = self._router.resolve(logical_model, required=required_caps, user_region=region)
            t0 = self._clock()
            try:
                resp = await asyncio.wait_for(
                    self._completion(model=entry.model, messages=messages, **provider_kw),
                    timeout=self._timeout,
                )
            except Exception as exc:  # provider failure incl. asyncio.TimeoutError
                failure_class = classify_failure(str(exc))
                latency = (self._clock() - t0) * 1000
                self._telemetry.record(
                    self._record(envelope, logical_model, entry, tokens=0, cost=0.0,
                                 latency=latency, degraded=True)
                )
                self._alerts.emit(
                    Alert(DEGRADED, {"model": logical_model, "provider": entry.backend,
                                     "failure_class": failure_class.value})
                )
                raise ProviderCallError(str(exc), failure_class=failure_class) from exc

            latency = (self._clock() - t0) * 1000
            data = resp.model_dump() if hasattr(resp, "model_dump") else resp
            usage = data.get("usage") or {}
            if not usage:  # cached/streaming responses can omit usage -> cost would be wrong
                self._alerts.emit(
                    Alert(DEGRADED, {"model": logical_model, "provider": entry.backend,
                                     "reason": "no_usage_metadata"})
                )
            tokens = int(usage.get("total_tokens", 0))
            cost = entry.pricing_per_mtok * tokens / 1_000_000
            self._telemetry.record(
                self._record(envelope, logical_model, entry, tokens=tokens, cost=cost,
                             latency=latency, degraded=False)
            )
            return GatewayResult(raw=resp, provider=entry.backend, tokens=tokens,
                                 cost_usd=cost, latency_ms=latency, degraded=False)
        finally:
            await self._quota.release(key)

    @staticmethod
    def _record(envelope, logical_model, entry, *, tokens, cost, latency, degraded) -> CallRecord:
        return CallRecord(
            tenant_id=envelope.tenant_id,
            user_id=envelope.user_id,
            device_id=envelope.device_id,
            logical_model=logical_model,
            provider=entry.backend,
            fallback_chain=(entry.backend,),
            degraded=degraded,
            source_mode=None,  # LLM call; context data-source mode is governed elsewhere
            tokens=tokens,
            cost_usd=cost,
            latency_ms=latency,
            data_flow_region=entry.residency_region,
        )
