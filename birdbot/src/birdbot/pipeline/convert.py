"""BirdEvent -> fast-stage input conversion (S15).

Maps the on-device Top-K to scored candidates and media refs to frames. Real per-frame
quality features (NIMA/BRISQUE/sharpness) are produced by an ordinary program elsewhere
(out of scope here), so frames default and the scorer's tie-break picks the first.
"""
from __future__ import annotations

from birdbot.ingress.schema import BirdEvent
from birdbot.recognition.types import FrameFeatures, ScoredCandidate


def candidates_from_topk(event: BirdEvent) -> list[ScoredCandidate]:
    return [ScoredCandidate(c.label, c.score) for c in event.top_k]


def frames_from_media(event: BirdEvent) -> list[FrameFeatures]:
    return [FrameFeatures(frame_id=url) for url in event.media]
