"""EU data-residency hard constraint (ADR-0007).

EU/UK user data may only go to an EU-region endpoint, or to a US endpoint that has
signed DPF/SCC; anything else (third countries without an adequacy decision, e.g. CN
endpoints) is blocked by default. This is a hard constraint, not a soft weight.
"""
from __future__ import annotations

from birdbot.router.registry import ModelEntry

_EU_USER_REGIONS = frozenset({"EU", "UK"})
_US_ADEQUACY_TAGS = frozenset({"dpf", "scc"})


def is_destination_allowed(*, user_region: str, entry: ModelEntry) -> bool:
    if user_region not in _EU_USER_REGIONS:
        return True  # non-EU/UK users: not constrained here (MVP)
    if entry.residency_region == "EU":
        return True
    if entry.residency_region == "US" and (entry.compliance_tags & _US_ADEQUACY_TAGS):
        return True
    return False
