"""Sensitive-species handling: coarse-grid their locations (ADR-0005 aligns with eBird's
~325 sensitive taxa / ~400 km² grid and GDPR data minimization).

The full eBird sensitive-species list is loaded operationally; this seed set keeps the
mechanism testable. Coarsening rounds coordinates to a ~20 km (~0.2°) cell.
"""
from __future__ import annotations

# Seed of sensitive taxa (the operational list is the eBird sensitive-species names).
SENSITIVE_SPECIES: frozenset[str] = frozenset(
    {
        "Strix occidentalis",   # spotted owl
        "Tyto alba",            # barn owl (nest sites)
        "Falco peregrinus",     # peregrine falcon (eyries)
    }
)

_CELL_DEGREES = 0.2  # ~22 km at the equator -> ~400 km² cell


def is_sensitive(species: str) -> bool:
    return species in SENSITIVE_SPECIES


def coarse_grid(lat: float, lon: float, *, cell_degrees: float = _CELL_DEGREES) -> str:
    """Round a coordinate down to a coarse grid cell label (location minimization)."""
    glat = round(lat / cell_degrees) * cell_degrees
    glon = round(lon / cell_degrees) * cell_degrees
    return f"{glat:.1f},{glon:.1f}"
