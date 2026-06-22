"""Shared value types for the fast-stage recognition pipeline."""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True, slots=True)
class ScoredCandidate:
    """A species candidate with a score. After Calibrator, score is a calibrated prob.

    ``taxon`` optionally carries the taxonomy (e.g. {"species","genus","family","order"})
    used for taxonomic rollup; on-device Top-K may not provide it.
    """

    label: str
    score: float
    taxon: Mapping[str, str] | None = None


@dataclass(frozen=True, slots=True)
class RecognitionDecision:
    """Adapter verdict: accept the top candidate, roll up to a higher taxon, or escalate
    to the (paid) upgrade backend in the deep stage."""

    action: str  # "accept" | "rollup" | "escalate"
    escalate: bool
    rollup_to: str | None
    reason: str


@dataclass(frozen=True, slots=True)
class RecognitionResult:
    candidates: list[ScoredCandidate]
    evidence: dict[str, Any]
    decision: RecognitionDecision


@dataclass(frozen=True, slots=True)
class FrameFeatures:
    """Per-frame quality features. Real values come from ordinary programs/models
    (NIMA aesthetic + BRISQUE/sharpness/motion-blur); the scorer just combines them."""

    frame_id: str
    aesthetic: float = 0.0     # NIMA, higher is better (0..1)
    sharpness: float = 0.0     # higher is better (0..1)
    motion_blur: float = 0.0   # lower is better (0..1)


@dataclass(frozen=True, slots=True)
class FastStageResult:
    candidates: list[ScoredCandidate]
    confidence: float
    decision: RecognitionDecision
    best_frame: FrameFeatures | None
    evidence: dict[str, Any] = field(default_factory=dict)
