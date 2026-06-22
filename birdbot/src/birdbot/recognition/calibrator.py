"""Confidence calibration via temperature scaling (ADR-0008).

Softmax probabilities are systematically overconfident, so we rescale before any
threshold/escalation decision. Treating each candidate score as a probability, we map
back to a logit (log p), divide by the temperature T, and re-softmax: T=1 just
renormalizes, T>1 softens overconfidence, all while preserving the ranking.
"""
from __future__ import annotations

import math

from birdbot.recognition.types import ScoredCandidate

_EPS = 1e-12


class Calibrator:
    def calibrate(
        self, candidates: list[ScoredCandidate], *, temperature: float
    ) -> list[ScoredCandidate]:
        if not candidates:
            return []
        if temperature <= 0:
            raise ValueError("temperature must be > 0")

        logits = [math.log(max(c.score, _EPS)) / temperature for c in candidates]
        ceiling = max(logits)
        exps = [math.exp(value - ceiling) for value in logits]
        total = sum(exps)
        calibrated = [
            ScoredCandidate(c.label, exp / total, c.taxon)
            for c, exp in zip(candidates, exps)
        ]
        return sorted(calibrated, key=lambda c: c.score, reverse=True)
