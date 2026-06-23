"""Story generation port + hard output contract + Skill methodology.

The StoryLLM port is a single structured call: prompt + curated frames + per-request tenant
envelope -> dict. The call is routed/governed by the LLMGateway the adapter holds (ADR-0014),
so the port no longer carries the real model. STORY_SKILL is the *methodology* (prose, no
enforcement); the enforceable contract is STORY_SCHEMA, validated in code (workflow).
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any, Protocol

from birdbot.tenant.context import TenantEnvelope

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
        envelope: TenantEnvelope,
        region: str = "US",
    ) -> dict[str, Any]: ...


def build_story_prompt(snapshot: Mapping[str, Any]) -> str:
    """Compose the deep-stage prompt: Skill methodology + structured evidence.

    Region is injected deterministically (from the device location) and the model is told
    not to infer it (S13); the explicit JSON instruction also satisfies providers whose
    json mode requires the word "json" in the prompt.
    """
    candidates = snapshot.get("candidates", [])
    rarity = snapshot.get("rarity", {})
    region = snapshot.get("region")
    evidence = snapshot.get("evidence", {})
    return (
        f"{STORY_SKILL}\n"
        f"Region (given, do not infer): {region}\n"
        f"Candidates: {candidates}\n"
        f"Local rarity: {rarity}\n"
        f"Evidence: {evidence}\n"
        "Return ONLY a JSON object with keys: behavior, rarity_narrative, story.\n"
    )
