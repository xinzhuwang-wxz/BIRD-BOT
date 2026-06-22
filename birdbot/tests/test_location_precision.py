"""Unit tests for location three-tier degradation (pure). raw is never persisted;
internal is a 5-20km grid (rarity only); public is city-level (display/log)."""
from __future__ import annotations

from birdbot.privacy.location import LocationPrecision, degrade_location


def test_raw_is_not_persisted():
    d = degrade_location(37.4219, -122.0841, LocationPrecision.RAW)
    assert d.persistable is False
    assert d.grid is None


def test_internal_collapses_nearby_points_into_one_grid():
    a = degrade_location(37.4219, -122.0841, LocationPrecision.INTERNAL)
    b = degrade_location(37.4250, -122.0850, LocationPrecision.INTERNAL)  # ~0.3 km away
    assert a.persistable is True
    assert a.grid == b.grid


def test_public_is_coarser_than_internal():
    # ~22 km apart: distinguishable at internal, collapsed at city-level public
    a_int = degrade_location(37.4, -122.0, LocationPrecision.INTERNAL)
    b_int = degrade_location(37.6, -122.0, LocationPrecision.INTERNAL)
    assert a_int.grid != b_int.grid

    a_pub = degrade_location(37.4, -122.0, LocationPrecision.PUBLIC)
    b_pub = degrade_location(37.6, -122.0, LocationPrecision.PUBLIC)
    assert a_pub.grid == b_pub.grid
