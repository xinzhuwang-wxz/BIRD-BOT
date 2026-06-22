"""Model capability registry (A5 / ADR-0007).

Maps a logical model / capability profile to one or more concrete backend entries, with
residency region and compliance tags as first-class fields (not soft weights). Multiple
entries per logical name are kept in registration order to drive fallback.
"""
from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from enum import Enum


class Capability(str, Enum):
    VISION = "vision"
    STRUCTURED_OUTPUT = "structured_output"
    PROMPT_CACHING = "prompt_caching"
    FUNCTION_CALLING = "function_calling"
    AUDIO = "audio"


@dataclass(frozen=True, slots=True)
class ModelEntry:
    logical_name: str
    backend: str
    model: str
    capabilities: frozenset[Capability]
    context_window: int
    pricing_per_mtok: float
    residency_region: str
    compliance_tags: frozenset[str]


class CapabilityRegistry:
    def __init__(self, entries: Iterable[ModelEntry]) -> None:
        self._by_logical: dict[str, list[ModelEntry]] = {}
        for entry in entries:
            self._by_logical.setdefault(entry.logical_name, []).append(entry)

    def entries_for(self, logical_name: str) -> list[ModelEntry]:
        """Entries registered for a logical name, in registration (fallback) order."""
        return list(self._by_logical.get(logical_name, []))
