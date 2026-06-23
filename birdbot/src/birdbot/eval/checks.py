"""Deterministic Story quality checks (G3) — no LLM, CI-regressable.

Each check returns issue strings (empty = clean). They guard against the failure modes a
generated Story is prone to: empty fields, no rarity language, a Story that doesn't actually
name the recognized bird, and region hallucination (S13 — the region is injected; the Story
must not invent a different one). Loose token matching keeps false positives low.
"""
from __future__ import annotations

import re
from typing import Any

from birdbot.eval.scenarios import EvalScenario

_RARITY_WORDS = ("common", "seasonal", "rare", "unusual", "uncommon", "frequent", "regular")


def check_story(story: dict[str, Any], scenario: EvalScenario) -> list[str]:
    issues: list[str] = []

    # 1. schema completeness (eval-level, beyond the hard schema gate)
    for key in ("behavior", "rarity_narrative", "story"):
        if not str(story.get(key, "")).strip():
            issues.append(f"empty:{key}")

    narrative = str(story.get("rarity_narrative", "")).lower()
    story_text = (str(story.get("story", "")) + " " + str(story.get("behavior", ""))).lower()

    # 2. rarity grounding: the narrative should use rarity language
    if not any(word in narrative for word in _RARITY_WORDS):
        issues.append("rarity:no-rarity-language")

    # 3. species grounding: the Story should name the recognized bird (loose token match)
    if scenario.expect_species and not any(
        token in story_text
        for species in scenario.expect_species
        for token in species.lower().split()
    ):
        issues.append("species:not-grounded")

    # 4. region grounding (S13): the Story must not name a region other than the given one.
    given = scenario.snapshot.get("region", "")
    full = (narrative + " " + story_text)
    other_regions = [
        r for r in _OTHER_REGION_TOKENS
        if re.search(rf"\b{r}\b", full) and r not in given.lower()
    ]
    if other_regions:
        issues.append(f"region:hallucinated:{','.join(other_regions)}")

    return issues


# A small guard set of place tokens that should never appear unless they ARE the given region.
# Region is deterministic (S13); a Story naming a different place is hallucinating.
_OTHER_REGION_TOKENS = ("taiwan", "europe", "australia", "africa", "japan", "alaska")
