"""Unit tests for ModelRouter.resolve: capability assertion, explicit rejection of the
four unimplemented backends, and the EU data-residency hard constraint (ADR-0007)."""
from __future__ import annotations

import pytest

from birdbot.router.registry import Capability, CapabilityRegistry, ModelEntry
from birdbot.router.router import ModelRouter, RoutingError, UnimplementedBackendError


def _entry(logical, backend, model, caps, region, tags):
    return ModelEntry(
        logical_name=logical,
        backend=backend,
        model=model,
        capabilities=frozenset(caps),
        context_window=200_000,
        pricing_per_mtok=1.0,
        residency_region=region,
        compliance_tags=frozenset(tags),
    )


def test_resolve_returns_first_capable_entry():
    reg = CapabilityRegistry(
        [_entry("fast-vision", "anthropic", "claude-haiku-4-5", {Capability.VISION}, "US", {"dpf"})]
    )
    entry = ModelRouter(reg).resolve("fast-vision", required={Capability.VISION})
    assert entry.backend == "anthropic"


def test_capability_assertion_skips_incapable_entry():
    reg = CapabilityRegistry(
        [
            _entry("fast-vision", "openai_compat", "gpt-v", {Capability.VISION}, "US", {"dpf"}),
            _entry(
                "fast-vision", "anthropic", "claude", {Capability.VISION, Capability.STRUCTURED_OUTPUT}, "US", {"dpf"}
            ),
        ]
    )
    entry = ModelRouter(reg).resolve(
        "fast-vision", required={Capability.VISION, Capability.STRUCTURED_OUTPUT}
    )
    assert entry.model == "claude"  # first entry lacks structured_output, skipped


def test_no_capable_entry_raises():
    reg = CapabilityRegistry(
        [_entry("fast-vision", "anthropic", "c", {Capability.VISION}, "US", {"dpf"})]
    )
    with pytest.raises(RoutingError):
        ModelRouter(reg).resolve("fast-vision", required={Capability.AUDIO})


def test_unimplemented_backend_is_explicitly_rejected():
    reg = CapabilityRegistry([_entry("x", "bedrock", "m", {Capability.VISION}, "US", {"dpf"})])
    with pytest.raises(UnimplementedBackendError):
        ModelRouter(reg).resolve("x", required={Capability.VISION})


def test_eu_user_data_blocked_from_third_country_endpoint():
    reg = CapabilityRegistry(
        [_entry("deep", "openai_compat", "qwen", {Capability.STRUCTURED_OUTPUT}, "CN", set())]
    )
    with pytest.raises(RoutingError):
        ModelRouter(reg).resolve("deep", required={Capability.STRUCTURED_OUTPUT}, user_region="EU")


def test_eu_user_allowed_to_eu_endpoint():
    reg = CapabilityRegistry(
        [_entry("deep", "anthropic", "claude-eu", {Capability.STRUCTURED_OUTPUT}, "EU", {"gdpr-adequate"})]
    )
    entry = ModelRouter(reg).resolve(
        "deep", required={Capability.STRUCTURED_OUTPUT}, user_region="EU"
    )
    assert entry.residency_region == "EU"


def test_eu_user_allowed_to_us_endpoint_with_dpf():
    reg = CapabilityRegistry(
        [_entry("deep", "anthropic", "claude-us", {Capability.STRUCTURED_OUTPUT}, "US", {"dpf"})]
    )
    entry = ModelRouter(reg).resolve(
        "deep", required={Capability.STRUCTURED_OUTPUT}, user_region="EU"
    )
    assert entry.model == "claude-us"
