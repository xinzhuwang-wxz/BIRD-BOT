"""Three-tier location precision degradation (方案 §3 / §contracts).

raw: never persisted (transient, ingress-only). internal: ~5-20 km grid, rarity use
only. public/log: city-level. Reuses the coarse-grid utility (also used for sensitive
species), at progressively coarser cell sizes.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from birdbot.context.sensitive import coarse_grid

_INTERNAL_CELL = 0.1  # ~11 km (within the 5-20 km band)
_PUBLIC_CELL = 0.5    # ~55 km, city-level


class LocationPrecision(str, Enum):
    RAW = "raw"
    INTERNAL = "internal"
    PUBLIC = "public"


@dataclass(frozen=True, slots=True)
class DegradedLocation:
    precision: LocationPrecision
    grid: str | None
    persistable: bool


def degrade_location(lat: float, lon: float, precision: LocationPrecision) -> DegradedLocation:
    if precision is LocationPrecision.RAW:
        return DegradedLocation(LocationPrecision.RAW, grid=None, persistable=False)
    cell = _INTERNAL_CELL if precision is LocationPrecision.INTERNAL else _PUBLIC_CELL
    return DegradedLocation(precision, grid=coarse_grid(lat, lon, cell_degrees=cell), persistable=True)
