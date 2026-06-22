"""BirdContextService: the governed orchestration over local-bird-context sources.

Selects sources by the explicit data-source mode, intercepts commercial use of
non-commercial sources, caches and rate-limits, and degrades to the next eligible source
on failure/quota — always surfacing the active mode and any degradation via an observer
(never silent, ADR-0006). Holds the API key inside its injected sources; the key never
leaves this layer.
"""
from __future__ import annotations

import time
from collections.abc import Callable, Mapping
from typing import Any

from birdbot.context.models import (
    SOURCE_POLICIES,
    BirdContext,
    ContextSource,
    SourceMode,
    rarity_label,
)

Observer = Callable[[dict[str, Any]], None]

_MODE_ORDER: dict[SourceMode, tuple[str, ...]] = {
    SourceMode.AUTO: ("ebird", "inaturalist", "taxonomy"),
    SourceMode.EBIRD_ONLY: ("ebird",),
    SourceMode.NON_EBIRD_ONLY: ("inaturalist", "taxonomy"),
}


class BirdContextService:
    def __init__(
        self,
        *,
        sources: Mapping[str, ContextSource],
        observer: Observer | None = None,
        cache_ttl: float = 3600.0,
        daily_quota: int = 500,
    ) -> None:
        self._sources = dict(sources)
        self._observer = observer
        self._cache_ttl = cache_ttl
        self._daily_quota = daily_quota
        self._cache: dict[tuple[str, str, str], tuple[BirdContext, float]] = {}
        self._calls = 0

    async def get_context(
        self,
        *,
        region: str,
        date: str,
        mode: SourceMode = SourceMode.AUTO,
        commercial: bool = False,
    ) -> BirdContext:
        diag: dict[str, Any] = {"mode": mode.value, "commercial": commercial}

        key = (region, date, mode.value)
        cached = self._cache.get(key)
        now = time.monotonic()
        if cached is not None and cached[1] > now:
            return cached[0]

        primary = _MODE_ORDER[mode][0]
        eligible: list[str] = []
        for name in _MODE_ORDER[mode]:
            if name not in self._sources:
                continue
            if commercial and not SOURCE_POLICIES[name].commercial_allowed:
                diag.setdefault("blocked", []).append(name)  # commercial interception
                continue
            eligible.append(name)

        if not eligible:
            return self._degraded(region, date, diag, reason="no_authorized_source")
        if self._calls >= self._daily_quota:
            return self._degraded(region, date, diag, reason="quota_exhausted")

        for name in eligible:
            self._calls += 1
            try:
                freqs = await self._sources[name].frequencies(region=region, date=date)
            except Exception as exc:  # circuit/degrade to the next eligible source
                diag.setdefault("failed", []).append(name)
                diag["last_error"] = str(exc)
                continue

            policy = SOURCE_POLICIES[name]
            labels = {species: rarity_label(freq) for species, freq in freqs.items()}
            degraded = name != primary
            diag.update(source_used=name, degraded=degraded)
            self._surface(diag)
            context = BirdContext(
                region=region,
                date=date,
                frequencies=dict(freqs),
                labels=labels,
                source=name,
                attribution=policy.attribution,
                degraded=degraded,
                diagnostics=dict(diag),
            )
            if policy.cacheable:
                self._cache[key] = (context, now + self._cache_ttl)
            return context

        return self._degraded(region, date, diag, reason="all_sources_failed")

    def _degraded(
        self, region: str, date: str, diag: dict[str, Any], *, reason: str
    ) -> BirdContext:
        diag.update(source_used=None, degraded=True, degraded_reason=reason)
        self._surface(diag)
        return BirdContext(
            region=region,
            date=date,
            frequencies={},
            labels={},
            source=None,
            attribution=None,
            degraded=True,
            diagnostics=dict(diag),
        )

    def _surface(self, diag: dict[str, Any]) -> None:
        if self._observer is not None:
            self._observer(dict(diag))
