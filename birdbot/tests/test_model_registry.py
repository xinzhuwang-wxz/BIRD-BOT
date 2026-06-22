"""Unit tests for the model capability registry (pure): logical-name lookup + the
region/compliance first-class fields (ADR-0007)."""
from __future__ import annotations

from birdbot.router.registry import Capability, CapabilityRegistry, ModelEntry

_FAST_VISION = ModelEntry(
    logical_name="fast-vision",
    backend="anthropic",
    model="claude-haiku-4-5",
    capabilities=frozenset({Capability.VISION, Capability.STRUCTURED_OUTPUT}),
    context_window=200_000,
    pricing_per_mtok=1.0,
    residency_region="US",
    compliance_tags=frozenset({"dpf", "scc"}),
)
_DEEP = ModelEntry(
    logical_name="deep-reasoning",
    backend="anthropic",
    model="claude-opus-4-8",
    capabilities=frozenset({Capability.STRUCTURED_OUTPUT, Capability.PROMPT_CACHING}),
    context_window=200_000,
    pricing_per_mtok=15.0,
    residency_region="EU",
    compliance_tags=frozenset({"gdpr-adequate"}),
)


def test_registry_returns_entries_for_a_logical_name():
    reg = CapabilityRegistry([_FAST_VISION, _DEEP])
    entries = reg.entries_for("fast-vision")
    assert [e.model for e in entries] == ["claude-haiku-4-5"]
    assert Capability.VISION in entries[0].capabilities


def test_unknown_logical_name_returns_empty():
    assert CapabilityRegistry([_FAST_VISION]).entries_for("nope") == []


def test_entry_carries_region_and_compliance_tags():
    reg = CapabilityRegistry([_FAST_VISION, _DEEP])
    deep = reg.entries_for("deep-reasoning")[0]
    assert deep.residency_region == "EU"
    assert "gdpr-adequate" in deep.compliance_tags


def test_multiple_entries_preserve_registration_order_for_fallback():
    alt = ModelEntry(
        logical_name="fast-vision",
        backend="openai_compat",
        model="gpt-vision",
        capabilities=frozenset({Capability.VISION}),
        context_window=128_000,
        pricing_per_mtok=2.0,
        residency_region="US",
        compliance_tags=frozenset({"dpf"}),
    )
    reg = CapabilityRegistry([_FAST_VISION, alt])
    assert [e.model for e in reg.entries_for("fast-vision")] == ["claude-haiku-4-5", "gpt-vision"]
