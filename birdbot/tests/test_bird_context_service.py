"""Unit tests for BirdContextService orchestration (injected source doubles, no HTTP).

Covers the three data-source modes, commercial-use interception, degrade/quota surfaced
(not silent), cache, and attribution.
"""
from __future__ import annotations

import pytest

from birdbot.context.models import RarityLabel, SourceMode
from birdbot.context.service import BirdContextService


class FakeSource:
    def __init__(self, name, freqs=None, *, fail=False):
        self.name = name
        self._freqs = freqs or {}
        self._fail = fail
        self.calls = 0

    async def frequencies(self, *, region, date):
        self.calls += 1
        if self._fail:
            raise RuntimeError("source down")
        return self._freqs


@pytest.mark.asyncio
async def test_auto_mode_uses_ebird_primary_with_attribution():
    svc = BirdContextService(sources={"ebird": FakeSource("ebird", {"robin": 0.5})})
    ctx = await svc.get_context(region="US-CA", date="2026-06-22", mode=SourceMode.AUTO)
    assert ctx.source == "ebird"
    assert ctx.labels["robin"] is RarityLabel.COMMON
    assert ctx.attribution == "Source: eBird.org"
    assert ctx.degraded is False


@pytest.mark.asyncio
async def test_commercial_use_blocks_non_commercial_sources_visibly():
    """Pre-authorization, both eBird and iNaturalist (CC BY-NC) are non-commercial, so a
    commercial request to a tenant with only those sources is fully blocked (ADR-0005)."""
    events = []
    svc = BirdContextService(
        sources={
            "ebird": FakeSource("ebird", {"robin": 0.5}),
            "inaturalist": FakeSource("inaturalist", {"robin": 0.3}),
        },
        observer=events.append,
    )
    ctx = await svc.get_context(
        region="US-CA", date="2026-06-22", mode=SourceMode.AUTO, commercial=True
    )
    assert ctx.source is None
    assert ctx.degraded is True
    assert set(ctx.diagnostics["blocked"]) == {"ebird", "inaturalist"}
    assert ctx.diagnostics["degraded_reason"] == "no_authorized_source"
    assert events  # surfaced, not silent


@pytest.mark.asyncio
async def test_commercial_use_degrades_to_commercial_safe_taxonomy():
    """Commercial use intercepts eBird but can fall back to the commercial-safe taxonomy
    baseline (names only, no frequency)."""
    svc = BirdContextService(
        sources={
            "ebird": FakeSource("ebird", {"robin": 0.5}),
            "taxonomy": FakeSource("taxonomy", {}),
        }
    )
    ctx = await svc.get_context(
        region="US-CA", date="2026-06-22", mode=SourceMode.AUTO, commercial=True
    )
    assert ctx.source == "taxonomy"
    assert ctx.degraded is True
    assert "ebird" in ctx.diagnostics["blocked"]


@pytest.mark.asyncio
async def test_ebird_only_commercial_is_fully_blocked():
    events = []
    svc = BirdContextService(
        sources={"ebird": FakeSource("ebird", {"robin": 0.5})}, observer=events.append
    )
    ctx = await svc.get_context(
        region="US-CA", date="2026-06-22", mode=SourceMode.EBIRD_ONLY, commercial=True
    )
    assert ctx.source is None
    assert ctx.degraded is True
    assert ctx.diagnostics["degraded_reason"] == "no_authorized_source"
    assert events


@pytest.mark.asyncio
async def test_non_ebird_only_never_touches_ebird():
    ebird = FakeSource("ebird", {"x": 0.9})
    svc = BirdContextService(
        sources={"ebird": ebird, "inaturalist": FakeSource("inaturalist", {"robin": 0.1})}
    )
    ctx = await svc.get_context(
        region="US-CA", date="2026-06-22", mode=SourceMode.NON_EBIRD_ONLY
    )
    assert ctx.source == "inaturalist"
    assert ebird.calls == 0
    assert ctx.degraded is False


@pytest.mark.asyncio
async def test_source_failure_degrades_to_next_and_surfaces():
    events = []
    svc = BirdContextService(
        sources={
            "ebird": FakeSource("ebird", fail=True),
            "inaturalist": FakeSource("inaturalist", {"robin": 0.1}),
        },
        observer=events.append,
    )
    ctx = await svc.get_context(region="US-CA", date="2026-06-22", mode=SourceMode.AUTO)
    assert ctx.source == "inaturalist"
    assert ctx.degraded is True
    assert "ebird" in ctx.diagnostics.get("failed", [])
    assert events


@pytest.mark.asyncio
async def test_cache_avoids_a_second_source_call():
    ebird = FakeSource("ebird", {"robin": 0.5})
    svc = BirdContextService(sources={"ebird": ebird})
    await svc.get_context(region="US-CA", date="2026-06-22")
    await svc.get_context(region="US-CA", date="2026-06-22")
    assert ebird.calls == 1  # second served from cache


@pytest.mark.asyncio
async def test_quota_exhaustion_degrades_visibly():
    events = []
    svc = BirdContextService(
        sources={"ebird": FakeSource("ebird", {"robin": 0.5})},
        observer=events.append,
        daily_quota=1,
    )
    await svc.get_context(region="R1", date="2026-06-22")  # consumes the only call
    ctx = await svc.get_context(region="R2", date="2026-06-22")  # exhausted
    assert ctx.degraded is True
    assert ctx.diagnostics["degraded_reason"] == "quota_exhausted"
    assert events
