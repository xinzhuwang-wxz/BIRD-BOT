"""Unit tests for BirdEvent -> fast-stage input conversion (S15). Pure."""
from __future__ import annotations

from birdbot.ingress.schema import BirdEvent
from birdbot.pipeline.convert import candidates_from_topk, frames_from_media


def _event(**kw):
    base = dict(tenant_id="t1", device_id="d1", event_id="e1")
    base.update(kw)
    return BirdEvent(**base)


def test_candidates_from_topk_preserve_label_and_score():
    cands = candidates_from_topk(
        _event(top_k=[{"label": "robin", "score": 0.8}, {"label": "sparrow", "score": 0.2}])
    )
    assert [(c.label, c.score) for c in cands] == [("robin", 0.8), ("sparrow", 0.2)]


def test_frames_from_media_one_frame_per_media_ref():
    frames = frames_from_media(_event(media=["https://cdn/a.jpg", "https://cdn/b.jpg"]))
    assert [f.frame_id for f in frames] == ["https://cdn/a.jpg", "https://cdn/b.jpg"]


def test_missing_media_yields_no_frames():
    assert frames_from_media(_event()) == []


def test_missing_topk_yields_no_candidates():
    assert candidates_from_topk(_event()) == []
