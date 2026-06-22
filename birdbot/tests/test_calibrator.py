"""Unit tests for the confidence Calibrator (temperature scaling). Pure, no I/O.

Softmax is systematically overconfident; we temperature-scale before any threshold is
applied (ADR-0008). These pin the observable contract, not the arithmetic.
"""
from __future__ import annotations

import pytest

from birdbot.recognition.calibrator import Calibrator
from birdbot.recognition.types import ScoredCandidate


def test_calibrated_probabilities_sum_to_one():
    out = Calibrator().calibrate(
        [ScoredCandidate("a", 0.9), ScoredCandidate("b", 0.1)], temperature=1.5
    )
    assert sum(c.score for c in out) == pytest.approx(1.0)


def test_temperature_one_keeps_normalized_ranking():
    out = Calibrator().calibrate(
        [ScoredCandidate("a", 0.8), ScoredCandidate("b", 0.2)], temperature=1.0
    )
    assert [c.label for c in out] == ["a", "b"]
    assert out[0].score == pytest.approx(0.8)


def test_higher_temperature_reduces_overconfidence():
    cands = [ScoredCandidate("a", 0.9), ScoredCandidate("b", 0.1)]
    base = Calibrator().calibrate(cands, temperature=1.0)
    hot = Calibrator().calibrate(cands, temperature=3.0)
    assert hot[0].label == "a"  # ranking preserved
    assert hot[0].score < base[0].score  # top-1 confidence softened


def test_single_candidate_is_certain():
    out = Calibrator().calibrate([ScoredCandidate("a", 0.4)], temperature=2.0)
    assert out[0].score == pytest.approx(1.0)


def test_empty_input_returns_empty():
    assert Calibrator().calibrate([], temperature=1.5) == []


def test_zero_score_does_not_crash():
    out = Calibrator().calibrate(
        [ScoredCandidate("a", 0.5), ScoredCandidate("b", 0.0)], temperature=1.5
    )
    assert sum(c.score for c in out) == pytest.approx(1.0)
    assert out[0].label == "a"
