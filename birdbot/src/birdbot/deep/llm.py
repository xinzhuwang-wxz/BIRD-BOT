"""StoryLLM adapters for the deep stage (#9), chosen via the Model Router (#6).

Two adapters implement the same StoryLLM port:
- ``LiteLLMStoryLLM`` (production default, ADR-0013): unified provider gateway via LiteLLM,
  giving one cost/routing path shared with AgentRuntime (litellm.completion_cost).
- ``OpenAICompatStoryLLM``: OpenAI-SDK backed; kept because the SDK takes an injectable
  ``http_client``, which the S14 record/replay httpx transport hooks for CI without a key.

Both send the prompt + curated frames (image parts) and parse the JSON answer (json-repair
tolerates trailing prose). The hard schema contract is enforced by run_deep_stage, not here.
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


def _default_completion() -> Any:
    import litellm

    return litellm.acompletion


class LiteLLMStoryLLM:
    """StoryLLM backed by LiteLLM (ADR-0013): unified provider gateway + auto cost.

    Same StoryLLM port as OpenAICompatStoryLLM, and the production default. ``completion``
    is injectable (defaults to litellm.acompletion) so unit tests run without a key.
    """

    def __init__(self, *, model: str, completion: Any = None) -> None:
        self.model = model
        self._completion = completion or _default_completion()

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

        response = await self._completion(
            model=self.model or model,
            messages=[{"role": "user", "content": content}],
            response_format={"type": "json_object"},
            max_tokens=800,
        )
        data = response.model_dump() if hasattr(response, "model_dump") else response
        raw = data["choices"][0]["message"]["content"] or ""
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return json.loads(repair_json(raw))


def build_story_llm(
    *, router: ModelRouter, completion: Any = None, user_region: str = "US"
) -> LiteLLMStoryLLM:
    """Resolve the deep-reasoning logical model via the Model Router, on LiteLLM (ADR-0013).

    The router maps the logical model + region/capabilities to a concrete backend model;
    LiteLLM supplies the unified provider gateway (credentials/endpoint via its config).
    """
    entry = router.resolve(
        _DEEP_REASONING, required=_REQUIRED_CAPS, user_region=user_region
    )
    return LiteLLMStoryLLM(model=entry.model, completion=completion)
