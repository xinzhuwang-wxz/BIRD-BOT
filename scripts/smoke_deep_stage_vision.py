"""Live deep-stage vision smoke (key from env): a real multimodal LLM reads a curated
frame + structured evidence and produces a structured Story.

This verifies the vision path the fake StoryLLM (#9) couldn't — the deep stage feeds the
model 3-8 curated frames + evidence and expects {behavior, rarity_narrative, story}
(STORY_SCHEMA), the hard contract enforced in code. Direct OpenAI-compatible SDK call
(ADR-0011: provider backend swappable / not locked). Key read from env, never on disk.

    LLM_API_KEY=ark-... LLM_BASE_URL=https://ark.cn-beijing.volces.com/api/v3 \
        LLM_MODEL=doubao-seed-2-0-pro-260215 python scripts/smoke_deep_stage_vision.py

Doubao is CN-residency: dev smoke only (ADR-0007).
"""
from __future__ import annotations

import asyncio
import base64
import json
import os
from pathlib import Path

# A real Eurasian blue tit photo (Wikimedia Commons, featured). Override via BIRD_IMAGE_URL.
# We fetch it locally and inline it as base64 so the model host doesn't have to reach an
# external URL (Ark times out fetching cross-border URLs).
_BIRD_IMAGE = os.environ.get(
    "BIRD_IMAGE_URL",
    "https://upload.wikimedia.org/wikipedia/commons/thumb/8/86/"
    "Eurasian_blue_tit_Lancashire.jpg/960px-Eurasian_blue_tit_Lancashire.jpg",
)


async def main() -> None:
    api_key = os.environ.get("LLM_API_KEY")
    if not api_key:
        raise SystemExit("set LLM_API_KEY (+ LLM_BASE_URL / LLM_MODEL)")
    api_base = os.environ.get("LLM_BASE_URL", "https://ark.cn-beijing.volces.com/api/v3")
    model = os.environ.get("LLM_MODEL", "doubao-seed-2-0-pro-260215")

    import httpx
    from birdbot.deep.llm import OpenAICompatStoryLLM
    from birdbot.deep.story import STORY_SCHEMA, STORY_SKILL
    from birdbot.router.validate import validate_structured_output
    from openai import AsyncOpenAI

    image_path = os.environ.get("BIRD_IMAGE_PATH")
    if image_path:
        img_bytes = Path(image_path).read_bytes()
    else:
        async with httpx.AsyncClient() as http:
            resp_img = await http.get(
                _BIRD_IMAGE,
                timeout=30,
                follow_redirects=True,
                headers={"User-Agent": "BirdBot-smoke/0.1 (dev; bird-feeder AI)"},
            )
            resp_img.raise_for_status()
            img_bytes = resp_img.content
    data_url = "data:image/jpeg;base64," + base64.b64encode(img_bytes).decode()

    # Structured evidence the main line would have prepared (fast stage + Bird Context).
    evidence = {
        "candidates": [["Cyanistes caeruleus", 0.94]],
        "rarity": {"Cyanistes caeruleus": "common"},
        "device_history": {"visits_30d": 8},
        "region": "US-CA",
    }
    prompt = (
        f"{STORY_SKILL}\n"
        f"Structured evidence: {json.dumps(evidence)}\n"
        "Use the attached curated frame and the evidence. "
        "Return ONLY a JSON object with keys: behavior, rarity_narrative, story."
    )

    # Use the production StoryLLM (S12): OpenAI-compatible, vision-capable.
    client = AsyncOpenAI(api_key=api_key, base_url=api_base)
    llm = OpenAICompatStoryLLM(client=client, model=model)
    story = await llm.generate(
        prompt=prompt, frames=[data_url], schema=STORY_SCHEMA, model=model
    )

    errors = validate_structured_output(story, STORY_SCHEMA)
    print(f"=== MODEL: {model} (vision) ===")
    print("=== STORY SCHEMA CHECK ===", "OK" if not errors else errors)
    print("=== STORY ===")
    print(json.dumps(story, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
