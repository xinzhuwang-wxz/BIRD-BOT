"""ModelRouter: resolve a logical model to a concrete backend with guardrails.

Walks the registry entries in fallback order, asserting required capabilities before
selecting (so a request is never sent to a backend that would silently downgrade it),
and enforcing the EU residency hard constraint. The four unimplemented backends are
rejected explicitly — the kernel factory would otherwise let them fall through to the
OpenAI-compatible path silently (factory.py:44,66).
"""
from __future__ import annotations

from collections.abc import Collection

from birdbot.router.region import is_destination_allowed
from birdbot.router.registry import Capability, CapabilityRegistry, ModelEntry

# Backends present in config history but with no implementation in meta-nanobot.
UNIMPLEMENTED_BACKENDS = frozenset({"bedrock", "azure_openai", "github_copilot", "openai_codex"})


class RoutingError(Exception):
    """No eligible backend for the requested logical model / region / capabilities."""


class UnimplementedBackendError(RoutingError):
    """An entry names a backend with no implementation (would silently misroute)."""


class ModelRouter:
    def __init__(self, registry: CapabilityRegistry) -> None:
        self._registry = registry

    def resolve(
        self,
        logical_name: str,
        *,
        required: Collection[Capability] = (),
        user_region: str = "US",
    ) -> ModelEntry:
        entries = self._registry.entries_for(logical_name)
        if not entries:
            raise RoutingError(f"no entries for logical model '{logical_name}'")

        required_set = frozenset(required)
        reasons: list[str] = []
        for entry in entries:
            if entry.backend in UNIMPLEMENTED_BACKENDS:
                # Fail fast: an unimplemented backend in the registry is a config error,
                # not something to silently skip.
                raise UnimplementedBackendError(
                    f"backend '{entry.backend}' for {entry.model} is not implemented"
                )
            if not required_set <= entry.capabilities:
                reasons.append(f"{entry.model}: missing {required_set - entry.capabilities}")
                continue
            if not is_destination_allowed(user_region=user_region, entry=entry):
                reasons.append(f"{entry.model}: residency {entry.residency_region} blocked for {user_region}")
                continue
            return entry

        raise RoutingError(f"no eligible backend for '{logical_name}': {reasons}")
