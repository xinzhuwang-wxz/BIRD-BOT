"""Unit tests for the fast-stage orchestration. Pure; ties the three components together.

Returns calibrated candidates + confidence + decision + best frame; degrades the best
frame to None when media is missing (缺媒体降级).
"""
from __future__ import annotations

from birdbot.recognition.fast_stage import run_fast_stage
from birdbot.recognition.types import FrameFeatures, ScoredCandidate


def test_end_to_end_returns_candidates_confidence_and_best_frame():
    res = run_fast_stage(
        raw_candidates=[ScoredCandidate("robin", 0.95), ScoredCandidate("sparrow", 0.05)],
        frames=[
            FrameFeatures("f1", aesthetic=0.9, sharpness=0.9, motion_blur=0.1),
            FrameFeatures("f2", aesthetic=0.1, sharpness=0.1, motion_blur=0.9),
        ],
    )
    assert res.candidates[0].label == "robin"
    assert res.confidence == res.candidates[0].score
    assert 0.0 < res.confidence <= 1.0
    assert res.best_frame.frame_id == "f1"
    assert res.decision.action == "accept"


def test_missing_media_degrades_best_frame_to_none():
    res = run_fast_stage(
        raw_candidates=[ScoredCandidate("robin", 0.95), ScoredCandidate("sparrow", 0.05)],
        frames=[],
    )
    assert res.best_frame is None  # degraded, no media
    assert res.candidates[0].label == "robin"  # recognition still runs
    assert res.decision.action == "accept"


def test_no_candidates_yields_zero_confidence_and_escalate():
    res = run_fast_stage(raw_candidates=[], frames=[])
    assert res.confidence == 0.0
    assert res.candidates == []
    assert res.decision.action == "escalate"
    assert res.best_frame is None
