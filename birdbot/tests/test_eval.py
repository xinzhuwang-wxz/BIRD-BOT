"""G3: deterministic Story quality checks + eval runner (no key, CI-regressable)."""
from __future__ import annotations

import pytest

from birdbot.eval.checks import check_story
from birdbot.eval.runner import pass_rate, run_eval
from birdbot.eval.scenarios import SCENARIOS

_SCN = SCENARIOS[0]  # common-feeder-visitor: expect "blue tit" / common, region US-CA
_GOOD = {
    "behavior": "feeding at the feeder",
    "rarity_narrative": "a common local visitor this time of year",
    "story": "A blue tit stopped by the feeder this morning.",
}


def test_clean_story_has_no_issues():
    assert check_story(_GOOD, _SCN) == []


def test_empty_field_flagged():
    assert "empty:story" in check_story({**_GOOD, "story": "  "}, _SCN)


def test_missing_rarity_language_flagged():
    bad = {**_GOOD, "rarity_narrative": "a lovely little bird"}  # no rarity word
    assert "rarity:no-rarity-language" in check_story(bad, _SCN)


def test_species_not_grounded_flagged():
    bad = {**_GOOD, "story": "A bird visited the feeder.", "behavior": "feeding"}  # no "blue tit"
    assert "species:not-grounded" in check_story(bad, _SCN)


def test_region_hallucination_flagged():
    bad = {**_GOOD, "story": "A blue tit, normally seen in Taiwan, visited."}  # region is US-CA
    assert any(i.startswith("region:hallucinated") for i in check_story(bad, _SCN))


@pytest.mark.asyncio
async def test_run_eval_passes_synthetic_good_story_across_scenarios():
    async def good_story(snapshot):
        species = snapshot["candidates"][0][0]
        rarity = next(iter(snapshot["rarity"].values()))
        return {
            "behavior": "feeding",
            "rarity_narrative": f"a {rarity} visitor in {snapshot['region']}",
            "story": f"A {species} visited the feeder this morning.",
        }

    results = await run_eval(SCENARIOS, good_story)

    assert len(results) == len(SCENARIOS)
    assert pass_rate(results) == 1.0  # synthetic good story clears every deterministic check


@pytest.mark.asyncio
async def test_run_eval_surfaces_a_bad_story():
    async def bad_story(_snapshot):
        return {"behavior": "", "rarity_narrative": "nice", "story": "A bird."}

    results = await run_eval([_SCN], bad_story)
    assert not results[0].passed
    assert "empty:behavior" in results[0].issues
