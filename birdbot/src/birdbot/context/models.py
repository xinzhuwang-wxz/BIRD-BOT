"""Value types for the Bird Context Service: source mode, authorization matrix, rarity
labels, the source port, and the context result."""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Protocol


class SourceMode(str, Enum):
    """Explicit data-source mode (ADR-0005). Each is independently debuggable."""

    AUTO = "auto"                      # eBird first (if authorized), else iNat, else taxonomy
    EBIRD_ONLY = "ebird-only"          # eBird only
    NON_EBIRD_ONLY = "non-ebird-only"  # iNat / taxonomy only (compliant baseline)


class RarityLabel(str, Enum):
    COMMON = "common"            # 当地常见
    SEASONAL = "seasonal"        # 季节访客
    RARE = "rare"                # 近期罕见


@dataclass(frozen=True, slots=True)
class SourcePolicy:
    """One row of the source × use × authorization matrix."""

    name: str
    cacheable: bool
    displayable: bool
    requires_attribution: bool
    attribution: str | None
    commercial_allowed: bool


# The authorization matrix. eBird/iNat data are non-commercial until licensed
# (ADR-0005); taxonomy (key-less reference) is commercial-safe.
SOURCE_POLICIES: dict[str, SourcePolicy] = {
    "ebird": SourcePolicy(
        "ebird", cacheable=True, displayable=True, requires_attribution=True,
        attribution="Source: eBird.org", commercial_allowed=False,
    ),
    "inaturalist": SourcePolicy(
        "inaturalist", cacheable=True, displayable=True, requires_attribution=True,
        attribution="Source: iNaturalist", commercial_allowed=False,
    ),
    "taxonomy": SourcePolicy(
        "taxonomy", cacheable=True, displayable=True, requires_attribution=False,
        attribution=None, commercial_allowed=True,
    ),
}

_COMMON_MIN = 0.2
_SEASONAL_MIN = 0.02


def rarity_label(frequency: float) -> RarityLabel:
    """Map a local occurrence frequency to a rarity label."""
    if frequency >= _COMMON_MIN:
        return RarityLabel.COMMON
    if frequency >= _SEASONAL_MIN:
        return RarityLabel.SEASONAL
    return RarityLabel.RARE


class ContextSource(Protocol):
    """An injected local-bird-context source (eBird/iNat/taxonomy adapter).

    Real HTTP adapters are wired separately; the service depends only on this port so it
    can be exercised with test doubles (and so eBird is never called pre-authorization).
    """

    name: str

    async def frequencies(self, *, region: str, date: str) -> Mapping[str, float]: ...


@dataclass(frozen=True, slots=True)
class BirdContext:
    """The context bundle returned for (region, date): per-species local frequency +
    rarity labels, plus the actual source, attribution, and degradation diagnostics."""

    region: str
    date: str
    frequencies: Mapping[str, float]
    labels: Mapping[str, RarityLabel]
    source: str | None
    attribution: str | None
    degraded: bool
    diagnostics: dict[str, Any] = field(default_factory=dict)
