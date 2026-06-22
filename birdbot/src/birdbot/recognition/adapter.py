"""Recognition Adapter (A3): the SpeciesNet-style four-stage tail.

calibrate (A2) -> geo/temporal rerank (a replaceable STUB in this slice) -> decide. The
decision is one of accept / rollup / escalate: a confident, well-separated top-1 is
accepted; a top-1/top-2 that are too close roll up to their common taxon and escalate;
an under-threshold top-1 escalates to the (paid) upgrade backend in the deep stage
(ADR-0008). Escalation thresholds are applied to CALIBRATED confidence.
"""
from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any

from birdbot.recognition.calibrator import Calibrator
from birdbot.recognition.types import (
    RecognitionDecision,
    RecognitionResult,
    ScoredCandidate,
)

Reranker = Callable[[list[ScoredCandidate], Mapping[str, Any] | None], list[ScoredCandidate]]

_TAXON_LEVELS = ("genus", "family", "order")


def _identity_rerank(
    candidates: list[ScoredCandidate], context: Mapping[str, Any] | None
) -> list[ScoredCandidate]:
    """Stub for the geo/temporal rerank — replaced by a real reranker in a later slice."""
    return list(candidates)


def _common_taxon(a: ScoredCandidate, b: ScoredCandidate) -> str | None:
    ta, tb = a.taxon or {}, b.taxon or {}
    for level in _TAXON_LEVELS:
        if ta.get(level) and ta.get(level) == tb.get(level):
            return ta[level]
    return None


class RecognitionAdapter:
    def __init__(
        self,
        *,
        calibrator: Calibrator | None = None,
        reranker: Reranker | None = None,
        accept_threshold: float = 0.7,
        margin: float = 0.1,
    ) -> None:
        self._calibrator = calibrator or Calibrator()
        self._rerank = reranker or _identity_rerank
        self._accept_threshold = accept_threshold
        self._margin = margin

    def recognize(
        self,
        raw_candidates: list[ScoredCandidate],
        *,
        temperature: float = 1.0,
        context: Mapping[str, Any] | None = None,
    ) -> RecognitionResult:
        calibrated = self._calibrator.calibrate(raw_candidates, temperature=temperature)
        reranked = self._rerank(calibrated, context)
        decision = self._decide(reranked)
        evidence = {
            "calibrated": [(c.label, c.score) for c in calibrated],
            "temperature": temperature,
            "context_used": context is not None,
        }
        return RecognitionResult(candidates=reranked, evidence=evidence, decision=decision)

    def _decide(self, candidates: list[ScoredCandidate]) -> RecognitionDecision:
        if not candidates:
            return RecognitionDecision("escalate", True, None, "no candidates")
        top1 = candidates[0]
        top2 = candidates[1] if len(candidates) > 1 else None
        if top2 is not None and (top1.score - top2.score) < self._margin:
            return RecognitionDecision(
                "rollup", True, _common_taxon(top1, top2), "top-1/top-2 too close"
            )
        if top1.score < self._accept_threshold:
            return RecognitionDecision(
                "escalate", True, None, "top-1 below accept threshold"
            )
        return RecognitionDecision("accept", False, None, "confident, well-separated top-1")
