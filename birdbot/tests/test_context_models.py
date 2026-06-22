"""Unit tests for Bird Context value types (pure): authorization matrix, rarity labels,
sensitive-species coarse grid."""
from __future__ import annotations

from birdbot.context.models import (
    SOURCE_POLICIES,
    RarityLabel,
    SourceMode,
    rarity_label,
)
from birdbot.context.sensitive import coarse_grid, is_sensitive


def test_ebird_policy_blocks_commercial_and_requires_attribution():
    ebird = SOURCE_POLICIES["ebird"]
    assert ebird.commercial_allowed is False  # pre-Cornell authorization (ADR-0005)
    assert ebird.requires_attribution is True
    assert ebird.attribution == "Source: eBird.org"


def test_taxonomy_is_commercial_safe():
    taxonomy = SOURCE_POLICIES["taxonomy"]
    assert taxonomy.commercial_allowed is True  # free, key-less


def test_source_mode_values():
    assert {m.value for m in SourceMode} == {"auto", "ebird-only", "non-ebird-only"}


def test_rarity_label_by_local_frequency():
    assert rarity_label(0.6) is RarityLabel.COMMON
    assert rarity_label(0.05) is RarityLabel.SEASONAL
    assert rarity_label(0.001) is RarityLabel.RARE
    assert rarity_label(0.0) is RarityLabel.RARE


def test_sensitive_species_detection():
    assert is_sensitive("Strix occidentalis") is True  # spotted owl, a sensitive taxon
    assert is_sensitive("Cyanistes caeruleus") is False


def test_coarse_grid_reduces_location_precision():
    precise_a = coarse_grid(37.4219, -122.0841)
    precise_b = coarse_grid(37.4300, -122.0900)  # ~1km away
    assert precise_a == precise_b  # collapsed into the same coarse cell
    assert "37.4219" not in precise_a  # full precision not retained
