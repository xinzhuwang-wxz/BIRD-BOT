"""Nature Chat handler: drive the open-layer AgentRuntime for one chat turn.

Builds a per-request tenant-scoped tool registry (device/region bound deterministically at
construction, never LLM-settable — 方案 §176) and runs the governed AgentRuntime over the
LLMGateway. Tool data is stubbed at MVP (G1); real device-history / rarity backends are a
follow-up. One handler per process; one runtime + registry per request.
"""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from birdbot.chat.registry import build_nature_chat_registry
from birdbot.runtime.agent import AgentRuntime
from birdbot.tenant.context import TenantEnvelope


class NatureChatHandler:
    def __init__(
        self,
        *,
        gateway: Any,
        alerts: Any,
        history: Mapping[str, Any] | None = None,
        rarity: Mapping[str, str] | None = None,
    ) -> None:
        self._gateway = gateway
        self._alerts = alerts
        self._history = dict(history or {})
        self._rarity = dict(rarity or {})

    async def handle(self, *, envelope: TenantEnvelope, prompt: str, region: str = "US") -> str:
        registry = build_nature_chat_registry(
            envelope=envelope, region=region, history=self._history, rarity=self._rarity
        )
        runtime = AgentRuntime(gateway=self._gateway, alerts=self._alerts)
        return await runtime.run(
            prompt=prompt, tools=registry.tools(), envelope=envelope, region=region
        )
