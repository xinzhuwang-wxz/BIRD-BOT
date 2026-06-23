"""StoryLLM adapter for the deep stage (#9): GatewayStoryLLM.

Builds the prompt + curated frames (image parts) and parses the JSON answer (json-repair
tolerates trailing prose). Routing / telemetry / quota / cost all happen inside the injected
LLMGateway (ADR-0014), so the deep stage is governed by construction; the OpenAI-SDK call
(for S14 record/replay) lives in ``runtime.completion`` as a governed completion adapter. The
hard schema contract is enforced by run_deep_stage, not here.
"""
from __future__ import annotations

import json
from collections.abc import Sequence
from typing import Any

from json_repair import repair_json

from birdbot.router.registry import Capability
from birdbot.tenant.context import TenantEnvelope

_DEEP_REASONING = "deep-reasoning"
_REQUIRED_CAPS = frozenset({Capability.VISION, Capability.STRUCTURED_OUTPUT})


class GatewayStoryLLM:
    """StoryLLM backed by the LLMGateway (ADR-0014): the production deep-stage adapter.

    Builds the vision messages and parses the JSON answer; routing / telemetry / quota /
    cost all happen inside the injected gateway, so the deep stage is governed by
    construction. The gateway resolves the logical model — this adapter never sees a real
    model name.
    """

    def __init__(self, *, gateway: Any, logical_model: str = _DEEP_REASONING) -> None:
        self._gateway = gateway
        self._logical_model = logical_model

    async def generate(
        self,
        *,
        prompt: str,
        frames: Sequence[str],
        envelope: TenantEnvelope,
        region: str = "US",
    ) -> dict[str, Any]:
        content: list[dict[str, Any]] = [{"type": "text", "text": prompt}]
        for frame in frames:
            content.append({"type": "image_url", "image_url": {"url": frame}})

        result = await self._gateway.complete(
            envelope=envelope,
            logical_model=self._logical_model,
            messages=[{"role": "user", "content": content}],
            skill="deep",
            required_caps=_REQUIRED_CAPS,
            region=region,
            response_format={"type": "json_object"},
            max_tokens=800,
        )
        data = result.raw.model_dump() if hasattr(result.raw, "model_dump") else result.raw
        raw = data["choices"][0]["message"]["content"] or ""
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return json.loads(repair_json(raw))


def build_story_llm(*, gateway: Any, logical_model: str = _DEEP_REASONING) -> GatewayStoryLLM:
    """Build the production deep-stage StoryLLM on the LLMGateway (ADR-0014).

    Routing (logical -> real model + region/capability) now happens inside the gateway, so
    this is a thin factory binding the gateway + the deep-reasoning logical model.
    """
    return GatewayStoryLLM(gateway=gateway, logical_model=logical_model)
