"""Unit tests for the unified redaction layer (pure): location degraded by precision,
sensitive species forced to coarse location, PII masked in free text."""
from __future__ import annotations

from birdbot.privacy.location import LocationPrecision
from birdbot.privacy.redaction import mask_pii, redact_event


def test_mask_pii_redacts_email_and_phone():
    masked = mask_pii("reach me@example.com or call +1 415 555 1234")
    assert "[email]" in masked
    assert "[phone]" in masked
    assert "example.com" not in masked


def test_redact_degrades_location_to_requested_precision():
    out = redact_event(
        {"location": {"lat": 37.4219, "lon": -122.0841}}, precision=LocationPrecision.PUBLIC
    )
    assert out["location"]["precision"] == "public"
    assert "lat" not in out["location"]  # raw coordinates removed


def test_raw_precision_drops_location_entirely():
    out = redact_event(
        {"location": {"lat": 37.4, "lon": -122.0}}, precision=LocationPrecision.RAW
    )
    assert out["location"] is None


def test_sensitive_species_forces_coarse_location():
    out = redact_event(
        {"species": "Strix occidentalis", "location": {"lat": 37.4219, "lon": -122.0841}},
        precision=LocationPrecision.INTERNAL,
    )
    assert out["location"]["precision"] == "sensitive"
    assert "37.4219" not in str(out["location"])


def test_masks_pii_in_free_text_fields():
    out = redact_event({"note": "owner email bob@host.org"}, precision=LocationPrecision.PUBLIC)
    assert "[email]" in out["note"]
