"""Production StoryLLM: an OpenAI-compatible, vision-capable implementation of the
StoryLLM port (#9), chosen via the Model Router (#6).

The deep stage sends the prompt + curated frames (image parts) and parses the JSON answer
(json-repair tolerates trailing prose). Provider backend is swappable: any
OpenAI-compatible vendor works through the injected client (ADR-0011). The hard schema
contract is enforced by run_deep_stage (#9), not here.
"""
from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from typing import Any

from json_repair import repair_json

from birdbot.router.registry import Capability
from birdbot.router.router import ModelRouter

_DEEP_REASONING = "deep-reasoning"
_REQUIRED_CAPS = frozenset({Capability.VISION, Capability.STRUCTURED_OUTPUT})


class OpenAICompatStoryLLM:
    """StoryLLM backed by an OpenAI-compatible (async) client with vision."""

    def __init__(self, *, client: Any, model: str) -> None:
        self._client = client
        self.model = model

    async def generate(
        self,
        *,
        prompt: str,
        frames: Sequence[str],
        schema: Mapping[str, Any],
        model: str,
    ) -> dict[str, Any]:
        content: list[dict[str, Any]] = [{"type": "text", "text": prompt}]
        for frame in frames:
            content.append({"type": "image_url", "image_url": {"url": frame}})

        response = await self._client.chat.completions.create(
            model=self.model or model,
            messages=[{"role": "user", "content": content}],
            response_format={"type": "json_object"},
            max_tokens=800,
        )
        raw = response.choices[0].message.content or ""
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return json.loads(repair_json(raw))


def build_story_llm(
    *, router: ModelRouter, client: Any, user_region: str = "US"
) -> OpenAICompatStoryLLM:
    """Resolve the deep-reasoning logical model via the Model Router and bind the client.

    The router maps the logical model + region/capabilities to a concrete backend model;
    the injected client supplies the credentials/endpoint (provider backend swappable).
    """
    entry = router.resolve(
        _DEEP_REASONING, required=_REQUIRED_CAPS, user_region=user_region
    )
    return OpenAICompatStoryLLM(client=client, model=entry.model)
