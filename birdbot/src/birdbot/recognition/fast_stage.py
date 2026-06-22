"""Fast-stage orchestration (A2+A3+A8): Top-K -> recognition -> best frame.

Pure composition of Calibrator/Adapter/FrameScorer; returns within milliseconds the
calibrated candidates, top-1 calibrated confidence, decision, and best frame. With no
frames it degrades the best-frame pick to None while recognition still runs.

Landing the candidate snapshot into Postgres and returning over HTTP (202) is wired
where ingress meets this stage — a later integration step, not this pure-logic slice.
"""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from birdbot.recognition.adapter import RecognitionAdapter
from birdbot.recognition.frame_scorer import FrameScorer
from birdbot.recognition.types import FastStageResult, FrameFeatures, ScoredCandidate


def run_fast_stage(
    *,
    raw_candidates: list[ScoredCandidate],
    frames: list[FrameFeatures],
    adapter: RecognitionAdapter | None = None,
    frame_scorer: FrameScorer | None = None,
    temperature: float = 1.0,
    context: Mapping[str, Any] | None = None,
) -> FastStageResult:
    adapter = adapter or RecognitionAdapter()
    frame_scorer = frame_scorer or FrameScorer()

    recognition = adapter.recognize(
        raw_candidates, temperature=temperature, context=context
    )
    best_frame = frame_scorer.select_best(frames)
    confidence = recognition.candidates[0].score if recognition.candidates else 0.0

    return FastStageResult(
        candidates=recognition.candidates,
        confidence=confidence,
        decision=recognition.decision,
        best_frame=best_frame,
        evidence=recognition.evidence,
    )
