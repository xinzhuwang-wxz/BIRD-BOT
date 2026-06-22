"""Unit tests for the Frame Scorer (best-frame pick). Pure, no I/O.

Features (NIMA aesthetic + sharpness + motion-blur) come from ordinary programs; the
scorer combines them and picks the best, degrading to None when there is no media.
"""
from __future__ import annotations

from birdbot.recognition.frame_scorer import FrameScorer
from birdbot.recognition.types import FrameFeatures


def test_selects_highest_combined_score():
    best = FrameScorer().select_best(
        [
            FrameFeatures("f1", aesthetic=0.9, sharpness=0.9, motion_blur=0.1),
            FrameFeatures("f2", aesthetic=0.2, sharpness=0.2, motion_blur=0.8),
        ]
    )
    assert best.frame_id == "f1"


def test_penalizes_motion_blur():
    sharp = FrameFeatures("sharp", aesthetic=0.5, sharpness=0.8, motion_blur=0.0)
    blurry = FrameFeatures("blurry", aesthetic=0.5, sharpness=0.8, motion_blur=0.9)
    assert FrameScorer().select_best([blurry, sharp]).frame_id == "sharp"


def test_empty_frames_degrade_to_none():
    assert FrameScorer().select_best([]) is None


def test_weights_are_configurable():
    fs = FrameScorer(w_aesthetic=1.0, w_sharpness=0.0, w_motion=0.0)
    best = fs.select_best(
        [FrameFeatures("b", aesthetic=0.1), FrameFeatures("a", aesthetic=0.9)]
    )
    assert best.frame_id == "a"
