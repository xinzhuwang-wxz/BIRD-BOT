"""Unified output/log redaction (方案 §188): location degraded by precision, sensitive
species forced to coarse location, PII masked — managed in one place."""
from __future__ import annotations

import re
from typing import Any

from birdbot.context.sensitive import coarse_grid, is_sensitive
from birdbot.privacy.location import LocationPrecision, degrade_location

_EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
_PHONE = re.compile(r"\+?\d[\d\s().-]{7,}\d")
_PII_TEXT_FIELDS = ("note", "caption", "description")
_SENSITIVE_CELL = 0.5  # never finer than city-level for sensitive species


def mask_pii(text: str) -> str:
    return _PHONE.sub("[phone]", _EMAIL.sub("[email]", text))


def redact_event(payload: dict[str, Any], *, precision: LocationPrecision) -> dict[str, Any]:
    """Return a redacted copy safe for output/logging."""
    out = dict(payload)

    location = out.get("location")
    has_coords = isinstance(location, dict) and "lat" in location and "lon" in location

    if has_coords and is_sensitive(out.get("species", "")):
        out["location"] = {
            "precision": "sensitive",
            "grid": coarse_grid(location["lat"], location["lon"], cell_degrees=_SENSITIVE_CELL),
        }
    elif has_coords:
        degraded = degrade_location(location["lat"], location["lon"], precision)
        out["location"] = (
            {"precision": degraded.precision.value, "grid": degraded.grid}
            if degraded.persistable
            else None
        )

    for field in _PII_TEXT_FIELDS:
        if isinstance(out.get(field), str):
            out[field] = mask_pii(out[field])

    return out
