"""Unit tests for the BirdEvent v0 schema (no DB/HTTP).

Pin only the observable contract: versioned, identity fields required, media/top_k
optional, and the tenant-scoped session_key derivation the facade consumes.
"""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from birdbot.ingress.schema import BirdEvent


def test_minimal_event_has_defaults():
    e = BirdEvent(tenant_id="t1", device_id="d1", event_id="e1")
    assert e.schema_version == "v0"
    assert e.media == []
    assert e.top_k == []
    assert e.user_id is None


def test_identity_fields_are_required():
    with pytest.raises(ValidationError):
        BirdEvent(tenant_id="", device_id="d1", event_id="e1")
    with pytest.raises(ValidationError):
        BirdEvent(tenant_id="t1", device_id="d1")  # missing event_id


def test_media_and_top_k_are_accepted():
    e = BirdEvent(
        tenant_id="t1",
        device_id="d1",
        event_id="e1",
        media=["https://cdn/img.jpg"],
        top_k=[{"label": "Cyanistes caeruleus", "score": 0.9}],
    )
    assert e.media == ["https://cdn/img.jpg"]
    assert e.top_k[0].label == "Cyanistes caeruleus"
    assert e.top_k[0].score == 0.9


def test_top_k_score_is_bounded():
    with pytest.raises(ValidationError):
        BirdEvent(
            tenant_id="t1",
            device_id="d1",
            event_id="e1",
            top_k=[{"label": "x", "score": 1.5}],
        )


def test_event_derives_tenant_scoped_session_key():
    e = BirdEvent(tenant_id="t1", user_id="u1", device_id="d1", event_id="e1")
    assert e.session_key == "tenant:t1:user:u1:device:d1"
