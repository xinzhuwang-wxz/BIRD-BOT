"""Eval scenarios: real backyard-feeder situations the deep stage should narrate well.

Each scenario is a deep-stage snapshot (candidates + local rarity + region) plus what a good
Story must reflect — the expected species (common-name tokens the Story should mention) and
the rarity label the narrative should be consistent with.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class EvalScenario:
    name: str
    snapshot: dict[str, Any]
    expect_species: tuple[str, ...]
    expect_rarity: str  # "common" | "seasonal" | "rare"


SCENARIOS: tuple[EvalScenario, ...] = (
    EvalScenario(
        name="common-feeder-visitor",
        snapshot={"candidates": [["blue tit", 0.92]], "rarity": {"blue tit": "common"},
                  "region": "US-CA", "evidence": {"device_history": {"visits_30d": 8}}},
        expect_species=("blue tit",),
        expect_rarity="common",
    ),
    EvalScenario(
        name="rare-sighting",
        snapshot={"candidates": [["painted bunting", 0.81]], "rarity": {"painted bunting": "rare"},
                  "region": "US-TX", "evidence": {"device_history": {"visits_30d": 1}}},
        expect_species=("painted bunting",),
        expect_rarity="rare",
    ),
    EvalScenario(
        name="seasonal-migrant",
        snapshot={"candidates": [["white-throated sparrow", 0.74]],
                  "rarity": {"white-throated sparrow": "seasonal"},
                  "region": "US-NY", "evidence": {"device_history": {"visits_30d": 3}}},
        expect_species=("sparrow",),
        expect_rarity="seasonal",
    ),
)
