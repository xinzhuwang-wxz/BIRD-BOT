"""Completion adapters for the LLMGateway (ADR-0014).

A ``Completion`` is ``async (model, messages, **kw) -> OpenAI-compatible response``. The
gateway holds one; ``litellm.acompletion`` is the production default. ``openai_sdk_completion``
is the OpenAI-SDK adapter — its HTTP transport is injectable, so the S14 record/replay
transport hooks it for CI without a key, and it doubles as the escape hatch if litellm
misbehaves. Either adapter still runs through the gateway, so the call stays governed.
"""
from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any


def openai_sdk_completion(
    *, api_key: str, base_url: str, transport: Any = None
) -> Callable[..., Awaitable[Any]]:
    """Build a Completion backed by the OpenAI SDK; ``transport`` hooks record/replay (S14)."""
    import httpx
    from openai import AsyncOpenAI

    http_client = httpx.AsyncClient(transport=transport) if transport is not None else None
    client = AsyncOpenAI(api_key=api_key, base_url=base_url, http_client=http_client)

    async def completion(*, model: str, messages: list[dict[str, Any]], **kw: Any) -> Any:
        return await client.chat.completions.create(model=model, messages=messages, **kw)

    return completion
