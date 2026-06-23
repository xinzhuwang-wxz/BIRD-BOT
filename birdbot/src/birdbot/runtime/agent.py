"""Thin agent runtime (ADR-0013/0014): LLM -> tool_calls -> execute -> loop, via the gateway.

Open-layer (Nature Chat) only — the main line runs on Workflow + StoryLLM. Every LLM
round-trip goes through the injected LLMGateway (governed: quota/route/telemetry/cost). Tool
errors (bad JSON args / hallucinated tool name / execute raising) are fed back to the model
as error observations rather than crashing; a gateway failure or max-iterations exhaustion
degrades to a human-friendly line and surfaces an alert — never silent (ADR-0006).
"""
from __future__ import annotations

import json
from collections.abc import Sequence
from typing import Any

from birdbot.observability.alerts import DEGRADED, Alert
from birdbot.runtime.gateway import ProviderCallError, QuotaExhaustedError
from birdbot.tenant.context import TenantEnvelope

_DEFAULT_DEGRADED = "Sorry, I couldn't finish that just now — please try again in a moment."


class AgentRuntime:
    def __init__(
        self,
        *,
        gateway: Any,
        alerts: Any,
        logical_model: str = "deep-reasoning",
        skill: str = "chat",
        max_iterations: int = 6,
        degraded_message: str = _DEFAULT_DEGRADED,
    ) -> None:
        self._gateway = gateway
        self._alerts = alerts
        self._logical_model = logical_model
        self._skill = skill
        self._max_iterations = max_iterations
        self._degraded = degraded_message

    async def run(
        self,
        *,
        prompt: str,
        tools: Sequence[Any],
        envelope: TenantEnvelope,
        region: str = "US",
        max_iterations: int | None = None,
    ) -> str:
        limit = max_iterations or self._max_iterations
        messages: list[dict[str, Any]] = [{"role": "user", "content": prompt}]
        tool_map = {t.name: t for t in tools}
        schemas = [
            {"type": "function", "function": {"name": t.name, "description": t.description,
                                              "parameters": t.parameters}}
            for t in tools
        ]

        for _ in range(limit):
            try:
                result = await self._gateway.complete(
                    envelope=envelope, logical_model=self._logical_model, messages=messages,
                    skill=self._skill, region=region, tools=schemas,
                )
            except (ProviderCallError, QuotaExhaustedError):
                # the gateway already surfaced an alert; degrade to a human line, don't crash
                return self._degraded

            data = result.raw.model_dump() if hasattr(result.raw, "model_dump") else result.raw
            choices = data.get("choices") or []
            if not choices:
                self._alerts.emit(Alert(DEGRADED, {"skill": self._skill, "reason": "no_choices"}))
                return self._degraded
            message = choices[0].get("message") or {}
            tool_calls = message.get("tool_calls")
            if not tool_calls:
                return message.get("content") or ""

            messages.append(
                {"role": "assistant", "content": message.get("content"), "tool_calls": tool_calls}
            )
            for call in tool_calls:
                observation = await self._run_tool(call, tool_map)
                messages.append(
                    {"role": "tool", "tool_call_id": call["id"], "content": observation}
                )

        # max iterations exhausted -> surface, never a silent empty string
        self._alerts.emit(Alert(DEGRADED, {"skill": self._skill, "reason": "max_iterations"}))
        return self._degraded

    async def _run_tool(self, call: dict[str, Any], tool_map: dict[str, Any]) -> str:
        """Run one tool call; turn any failure into an error observation fed back to the model."""
        fn = call["function"]
        name = fn["name"]
        try:
            args = json.loads(fn["arguments"]) if fn.get("arguments") else {}
        except (json.JSONDecodeError, TypeError) as exc:
            self._alerts.emit(Alert(DEGRADED, {"tool": name, "reason": "bad_arguments"}))
            return f"ERROR: invalid arguments for {name}: {exc}"

        tool = tool_map.get(name)
        if tool is None:
            self._alerts.emit(Alert(DEGRADED, {"tool": name, "reason": "unknown_tool"}))
            return f"ERROR: unknown tool {name}"

        try:
            return str(await tool.execute(**args))
        except Exception as exc:
            self._alerts.emit(Alert(DEGRADED, {"tool": name, "reason": "tool_failed"}))
            return f"ERROR: tool {name} failed: {exc}"
