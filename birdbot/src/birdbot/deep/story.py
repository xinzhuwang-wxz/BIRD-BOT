"""Story generation port + hard output contract + Skill methodology.

The StoryLLM port is a single structured call: prompt + curated frames + schema -> dict.
STORY_SKILL is the *methodology* (prose, no enforcement); the enforceable contract is
STORY_SCHEMA, validated in code (workflow), not in the Skill.
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any, Protocol

MAX_FRAMES = 8  # multimodal LLM receives only 3-8 curated frames

# Skill methodology (prose). In production this can be externalized to a SKILL.md loaded
# by the kernel SkillsLoader; either way it carries no hard constraints.
STORY_SKILL = """\
You are narrating a single bird visit for a backyard feeder owner.
- behavior: infer what the bird is doing (feeding / vigilant / courtship / bathing …)
  from the candidates and evidence; hedge when uncertain.
- rarity_narrative: explain why this species shows up here now, using the local rarity
  labels (common / seasonal / rare). Do not overclaim.
- story: a short, warm, documentary-style paragraph tying it together.
Use only the curated frames and structured evidence provided; never invent media.
"""

STORY_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "behavior": {"type": "string"},
        "rarity_narrative": {"type": "string"},
        "story": {"type": "string"},
    },
    "required": ["behavior", "rarity_narrative", "story"],
}


class StoryLLM(Protocol):
    async def generate(
        self,
        *,
        prompt: str,
        frames: Sequence[str],
        schema: Mapping[str, Any],
        model: str,
    ) -> dict[str, Any]: ...


def build_story_prompt(snapshot: Mapping[str, Any]) -> str:
    """Compose the deep-stage prompt: Skill methodology + structured evidence."""
    candidates = snapshot.get("candidates", [])
    rarity = snapshot.get("rarity", {})
    evidence = snapshot.get("evidence", {})
    return (
        f"{STORY_SKILL}\n"
        f"Candidates: {candidates}\n"
        f"Local rarity: {rarity}\n"
        f"Evidence: {evidence}\n"
    )
