"""Unit tests for the Recognition Adapter (calibrate -> rerank stub -> decide). Pure.

Pins the decision contract (accept / rollup / escalate), that the geo/temporal rerank
is a replaceable stub, and that evidence is surfaced.
"""
from __future__ import annotations

from birdbot.recognition.adapter import RecognitionAdapter
from birdbot.recognition.types import ScoredCandidate


def test_high_confidence_top1_is_accepted():
    adapter = RecognitionAdapter(accept_threshold=0.6, margin=0.1)
    res = adapter.recognize(
        [ScoredCandidate("robin", 0.95), ScoredCandidate("sparrow", 0.05)],
        temperature=1.0,
    )
    assert res.decision.action == "accept"
    assert res.decision.escalate is False
    assert res.candidates[0].label == "robin"


def test_close_top1_top2_rolls_up_to_common_taxon_and_escalates():
    adapter = RecognitionAdapter(accept_threshold=0.6, margin=0.2)
    res = adapter.recognize(
        [
            ScoredCandidate("Cyanistes caeruleus", 0.5, {"genus": "Cyanistes", "family": "Paridae"}),
            ScoredCandidate("Cyanistes cyanus", 0.48, {"genus": "Cyanistes", "family": "Paridae"}),
        ],
        temperature=1.0,
    )
    assert res.decision.action == "rollup"
    assert res.decision.escalate is True
    assert res.decision.rollup_to == "Cyanistes"


def test_low_confidence_escalates_without_rollup():
    adapter = RecognitionAdapter(accept_threshold=0.9, margin=0.05)
    res = adapter.recognize(
        [ScoredCandidate("a", 0.6), ScoredCandidate("b", 0.1)], temperature=1.0
    )
    assert res.decision.action == "escalate"
    assert res.decision.rollup_to is None


def test_geo_temporal_reranker_is_replaceable():
    def reverse_rerank(cands, context):
        return list(reversed(cands))

    adapter = RecognitionAdapter(reranker=reverse_rerank)
    res = adapter.recognize(
        [ScoredCandidate("a", 0.9), ScoredCandidate("b", 0.1)], temperature=1.0
    )
    assert res.candidates[0].label == "b"  # decision follows the reranked order


def test_evidence_surfaces_calibrated_scores_and_context_use():
    adapter = RecognitionAdapter()
    res = adapter.recognize(
        [ScoredCandidate("a", 0.8), ScoredCandidate("b", 0.2)],
        temperature=1.5,
        context={"region": "US-CA"},
    )
    assert "calibrated" in res.evidence
    assert res.evidence["context_used"] is True


def test_no_candidates_escalates():
    res = RecognitionAdapter().recognize([], temperature=1.0)
    assert res.decision.action == "escalate"
    assert res.candidates == []
