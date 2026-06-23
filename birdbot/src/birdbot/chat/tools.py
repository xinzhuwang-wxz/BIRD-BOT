"""Nature Chat domain tools: self-hosted Tools the AgentRuntime can call across turns.

Deterministic context (device/region) is bound at construction and is NOT an LLM parameter
(方案 §176: tenant/device context flows only through deterministic components, never carried
by the LLM — a live smoke caught DeepSeek inventing region="Taiwan" when region was free).

The data comes from an injected async lookup, so the tool is decoupled from its backend:
production wires events-history / Bird Context Service lookups; tests use ``dict_visits`` /
``dict_rarity`` over a stub map.
"""
from __future__ import annotations

import json
from collections.abc import Awaitable, Callable, Mapping
from typing import Any

from birdbot.runtime.tool import Tool, tool_parameters

VisitsLookup = Callable[[str, str | None], Awaitable[Any]]  # (species, device_id) -> data
RarityLookup = Callable[[str, str], Awaitable[str]]  # (species, region) -> rarity label


def dict_visits(history: Mapping[str, Any]) -> VisitsLookup:
    """A VisitsLookup over a stub map (tests / MVP)."""

    async def lookup(species: str, _device_id: str | None) -> Any:
        return history.get(species, {"visits_30d": 0})

    return lookup


def dict_rarity(rarity: Mapping[str, str]) -> RarityLookup:
    """A RarityLookup over a stub map (tests / MVP)."""

    async def lookup(species: str, _region: str) -> str:
        return rarity.get(species, "unknown")

    return lookup


@tool_parameters(
    {
        "type": "object",
        "properties": {"species": {"type": "string"}},
        "required": ["species"],
    }
)
class DeviceHistoryTool(Tool):
    """How often a species visited this device recently. The device is bound here, never an
    LLM parameter; data comes from the injected lookup."""

    def __init__(self, lookup: VisitsLookup, *, device_id: str | None = None) -> None:
        self._lookup = lookup
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
        return json.dumps(await self._lookup(species, self._device_id))


@tool_parameters(
    {
        "type": "object",
        "properties": {"species": {"type": "string"}},
        "required": ["species"],
    }
)
class BirdContextTool(Tool):
    """Local rarity (common/seasonal/rare) for a species. ``region`` is bound deterministically
    (the device's post-degradation location), NOT an LLM parameter; data via the lookup."""

    def __init__(self, lookup: RarityLookup, *, region: str) -> None:
        self._lookup = lookup
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
            {"rarity": await self._lookup(species, self._region), "region": self._region}
        )
