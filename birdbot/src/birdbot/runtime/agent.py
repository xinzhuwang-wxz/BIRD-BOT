"""Thin agent runtime (ADR-0013): LLM -> tool_calls -> execute -> loop, on LiteLLM.

Replaces nanobot's AgentLoop for the open interaction layer. ``completion`` is injectable
(defaults to litellm.acompletion) so tests run without a key/network. Tools are duck-typed
(.name / .description / .parameters / async .execute(**kwargs)) — no nanobot dependency.
"""
from __future__ import annotations

import json
from collections.abc import Awaitable, Callable, Sequence
from typing import Any


def _default_completion() -> Callable[..., Awaitable[Any]]:
    import litellm

    return litellm.acompletion


class AgentRuntime:
    def __init__(
        self,
        *,
        model: str,
        completion: Callable[..., Awaitable[Any]] | None = None,
        max_iterations: int = 6,
    ) -> None:
        self._model = model
        self._completion = completion or _default_completion()
        self._max_iterations = max_iterations

    async def run(self, *, prompt: str, tools: Sequence[Any], max_iterations: int | None = None) -> str:
        limit = max_iterations or self._max_iterations
        messages: list[dict[str, Any]] = [{"role": "user", "content": prompt}]
        tool_map = {t.name: t for t in tools}
        schemas = [
            {
                "type": "function",
                "function": {
                    "name": t.name,
                    "description": t.description,
                    "parameters": t.parameters,
                },
            }
            for t in tools
        ]

        for _ in range(limit):
            resp = await self._completion(model=self._model, messages=messages, tools=schemas)
            data = resp.model_dump() if hasattr(resp, "model_dump") else resp
            message = data["choices"][0]["message"]
            tool_calls = message.get("tool_calls")
            if not tool_calls:
                return message.get("content") or ""

            messages.append(
                {"role": "assistant", "content": message.get("content"), "tool_calls": tool_calls}
            )
            for call in tool_calls:
                fn = call["function"]
                args = json.loads(fn["arguments"]) if fn.get("arguments") else {}
                result = await tool_map[fn["name"]].execute(**args)
                messages.append(
                    {"role": "tool", "tool_call_id": call["id"], "content": str(result)}
                )

        return ""
