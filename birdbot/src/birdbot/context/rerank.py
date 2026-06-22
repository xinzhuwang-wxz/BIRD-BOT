"""Geo/temporal reranker — the real replacement for the RecognitionAdapter's rerank stub.

Reweights calibrated candidates by the local occurrence frequency (the P(species|cell,
week) prior, à la Merlin/SpeciesNet) and renormalizes. A species with no local records is
multiplied by 1 (not zeroed), so genuinely-rare-but-real locals are not suppressed.
"""
from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any

from birdbot.context.models import BirdContext
from birdbot.recognition.types import ScoredCandidate

Reranker = Callable[[list[ScoredCandidate], Mapping[str, Any] | None], list[ScoredCandidate]]


def make_geo_temporal_reranker(context: BirdContext) -> Reranker:
    frequencies = context.frequencies

    def rerank(
        candidates: list[ScoredCandidate], _ctx: Mapping[str, Any] | None
    ) -> list[ScoredCandidate]:
        if not candidates:
            return []
        boosted = [
            ScoredCandidate(c.label, c.score * (1.0 + frequencies.get(c.label, 0.0)), c.taxon)
            for c in candidates
        ]
        total = sum(c.score for c in boosted) or 1.0
        normalized = [ScoredCandidate(c.label, c.score / total, c.taxon) for c in boosted]
        return sorted(normalized, key=lambda c: c.score, reverse=True)

    return rerank
