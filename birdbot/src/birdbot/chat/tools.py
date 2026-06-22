"""Nature Chat domain tools: self-hosted Tools the AgentRuntime can call across turns.

Stub data — the point is to exercise multi-turn tool orchestration, not the data sources
(which the main-line modules already cover).

Deterministic context (region/device) is bound at construction and NOT exposed as an LLM
parameter, so the model can't hallucinate it (方案 §176: tenant/device context flows only
through deterministic components, never carried by the LLM). A live smoke caught DeepSeek
inventing region="Taiwan" when region was a free parameter — binding it fixes that.
"""
from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from birdbot.runtime.tool import Tool, tool_parameters


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

    def __init__(self, history: Mapping[str, Any], *, device_id: str | None = None) -> None:
        self._history = dict(history)
        self._device_id = device_id  # bound per-request; never an LLM parameter
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
        self.calls.append({"species": species, "device_id": self._device_id})
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
