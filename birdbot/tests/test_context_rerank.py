"""The Bird Context geo/temporal reranker plugged into the RecognitionAdapter.

Injected source double (no real HTTP). Verifies local frequency reorders candidates and
that rarity labels come from the context, without suppressing species lacking local data.
"""
from __future__ import annotations

import pytest

from birdbot.context.models import RarityLabel
from birdbot.context.rerank import make_geo_temporal_reranker
from birdbot.context.service import BirdContextService
from birdbot.recognition.adapter import RecognitionAdapter
from birdbot.recognition.calibrator import Calibrator
from birdbot.recognition.types import ScoredCandidate


class FakeSource:
    def __init__(self, name, freqs):
        self.name = name
        self._freqs = freqs

    async def frequencies(self, *, region, date):
        return self._freqs


@pytest.mark.asyncio
async def test_local_frequency_reranks_toward_locally_common_species():
    svc = BirdContextService(
        sources={"ebird": FakeSource("ebird", {"sparrow": 0.8, "robin": 0.01})}
    )
    context = await svc.get_context(region="US-CA", date="2026-06-22")
    adapter = RecognitionAdapter(
        reranker=make_geo_temporal_reranker(context), accept_threshold=0.3, margin=0.01
    )

    res = adapter.recognize(
        [ScoredCandidate("robin", 0.55), ScoredCandidate("sparrow", 0.45)], temperature=1.0
    )
    assert res.candidates[0].label == "sparrow"  # locally common species promoted
    assert context.labels["sparrow"] is RarityLabel.COMMON
    assert context.labels["robin"] is RarityLabel.RARE


@pytest.mark.asyncio
async def test_reranker_does_not_suppress_species_without_local_data():
    svc = BirdContextService(sources={"ebird": FakeSource("ebird", {})})  # no local records
    context = await svc.get_context(region="US-CA", date="2026-06-22")
    reranker = make_geo_temporal_reranker(context)

    calibrated = Calibrator().calibrate(
        [ScoredCandidate("rarebird", 0.9), ScoredCandidate("other", 0.1)], temperature=1.0
    )
    out = reranker(calibrated, None)
    assert out[0].label == "rarebird"  # not zeroed despite no local data
