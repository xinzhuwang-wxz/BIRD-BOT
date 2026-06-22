"""Nature Chat domain tools (spike): nanobot Tools the agent loop can call across turns.

Stub data — the point is to exercise nanobot's multi-turn tool orchestration, not the
data sources (which the main-line modules already cover).

Deterministic context (region/device) is bound at construction and NOT exposed as an LLM
parameter, so the model can't hallucinate it (方案 §176: tenant/device context flows only
through deterministic components, never carried by the LLM). A live smoke caught DeepSeek
inventing region="Taiwan" when region was a free parameter — binding it fixes that.
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
    """How often a species visited this device recently.

    The device is implicit (this request's device) — never an LLM parameter.
    """

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
        species = kwargs.get("species", "")
        self.calls.append({"species": species})
        return json.dumps(self._history.get(species, {"visits_30d": 0}))


@tool_parameters(
    {
        "type": "object",
        "properties": {"species": {"type": "string"}},
        "required": ["species"],
    }
)
class BirdContextTool(Tool):
    """Local rarity (common/seasonal/rare) for a species.

    ``region`` is bound deterministically at construction (from the device's
    post-degradation location), NOT an LLM parameter — so the model cannot hallucinate it.
    """

    def __init__(self, rarity: Mapping[str, str], *, region: str) -> None:
        self._rarity = dict(rarity)
        self._region = region
        self.calls: list[dict[str, Any]] = []

    @property
    def name(self) -> str:
        return "bird_context"

    @property
    def description(self) -> str:
        return "Look up whether a species is locally common, seasonal, or rare for this device's area."

    @property
    def read_only(self) -> bool:
        return True

    async def execute(self, **kwargs: Any) -> str:
        species = kwargs.get("species", "")
        self.calls.append({"species": species, "region": self._region})
        return json.dumps(
            {"rarity": self._rarity.get(species, "unknown"), "region": self._region}
        )
