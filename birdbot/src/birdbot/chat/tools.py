"""Nature Chat domain tools (spike): nanobot Tools the agent loop can call across turns.

Stub data — the point is to exercise nanobot's multi-turn tool orchestration, not the
data sources (which the main-line modules already cover).
"""
from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from nanobot.agent.tools.base import Tool, tool_parameters


@tool_parameters(
    {
        "type": "object",
        "properties": {"species": {"type": "string"}},
        "required": ["species"],
    }
)
class DeviceHistoryTool(Tool):
    """How often a species visited this device recently."""

    def __init__(self, history: Mapping[str, Any]) -> None:
        self._history = dict(history)
        self.calls: list[dict[str, Any]] = []

    @property
    def name(self) -> str:
        return "device_history"

    @property
    def description(self) -> str:
        return "Look up how often a species has visited this device in the last 30 days."

    @property
    def read_only(self) -> bool:
        return True

    async def execute(self, **kwargs: Any) -> str:
        self.calls.append(kwargs)
        return json.dumps(self._history.get(kwargs.get("species", ""), {"visits_30d": 0}))


@tool_parameters(
    {
        "type": "object",
        "properties": {"species": {"type": "string"}, "region": {"type": "string"}},
        "required": ["species"],
    }
)
class BirdContextTool(Tool):
    """Local rarity (common/seasonal/rare) for a species."""

    def __init__(self, rarity: Mapping[str, str]) -> None:
        self._rarity = dict(rarity)
        self.calls: list[dict[str, Any]] = []

    @property
    def name(self) -> str:
        return "bird_context"

    @property
    def description(self) -> str:
        return "Look up whether a species is locally common, seasonal, or rare."

    @property
    def read_only(self) -> bool:
        return True

    async def execute(self, **kwargs: Any) -> str:
        self.calls.append(kwargs)
        return json.dumps({"rarity": self._rarity.get(kwargs.get("species", ""), "unknown")})
