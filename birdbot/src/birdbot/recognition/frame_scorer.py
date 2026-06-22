"""Best-frame selection (A8). Pure logic over per-frame quality features.

Real features (NIMA aesthetic, sharpness, motion blur) are produced by ordinary
programs/models elsewhere; this just combines them into one score and picks the best,
degrading to None when there are no frames (missing media).
"""
from __future__ import annotations

from birdbot.recognition.types import FrameFeatures


class FrameScorer:
    def __init__(
        self,
        *,
        w_aesthetic: float = 0.5,
        w_sharpness: float = 0.3,
        w_motion: float = 0.2,
    ) -> None:
        self._w_aesthetic = w_aesthetic
        self._w_sharpness = w_sharpness
        self._w_motion = w_motion

    def score(self, frame: FrameFeatures) -> float:
        return (
            self._w_aesthetic * frame.aesthetic
            + self._w_sharpness * frame.sharpness
            + self._w_motion * (1.0 - frame.motion_blur)
        )

    def select_best(self, frames: list[FrameFeatures]) -> FrameFeatures | None:
        if not frames:
            return None
        return max(frames, key=self.score)
