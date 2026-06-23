"""Per-request tenant-scoped ToolRegistry + deterministic context binding (S13).

tenant/user/device/region are bound at construction from the TenantEnvelope and are NOT
LLM-settable parameters — the model cannot override or hallucinate them (方案 §176)."""
from __future__ import annotations

import pytest

from birdbot.chat.registry import build_nature_chat_registry
from birdbot.chat.tools import DeviceHistoryTool, dict_rarity, dict_visits
from birdbot.tenant.context import TenantEnvelope


@pytest.mark.asyncio
async def test_device_history_uses_bound_device_ignoring_llm_arg():
    tool = DeviceHistoryTool(dict_visits({"robin": {"visits_30d": 3}}), device_id="d1")
    # An LLM that tries to pass a different device is ignored; the bound device is used.
    await tool.execute(species="robin", device_id="attacker-device")
    assert tool.calls == [{"species": "robin", "device_id": "d1"}]


def test_device_history_schema_does_not_expose_device():
    props = DeviceHistoryTool(dict_visits({}), device_id="d1").parameters["properties"]
    assert "device_id" not in props and "device" not in props


def test_build_registry_binds_envelope_and_region():
    envelope = TenantEnvelope(tenant_id="t1", user_id="u1", device_id="d1")
    registry = build_nature_chat_registry(
        envelope=envelope,
        region="US-CA",
        visits=dict_visits({"robin": {"visits_30d": 3}}),
        rarity=dict_rarity({"robin": "rare"}),
    )
    assert registry.has("device_history") and registry.has("bird_context")
    # neither tool exposes the bound context to the LLM
    assert "device_id" not in registry.get("device_history").parameters["properties"]
    assert "region" not in registry.get("bird_context").parameters["properties"]


@pytest.mark.asyncio
async def test_bound_region_ignores_llm_supplied_region():
    envelope = TenantEnvelope(tenant_id="t1", device_id="d1")
    registry = build_nature_chat_registry(
        envelope=envelope, region="US-CA",
        visits=dict_visits({}), rarity=dict_rarity({"robin": "common"}),
    )
    context = registry.get("bird_context")
    await context.execute(species="robin", region="hacker-region")  # LLM arg ignored
    assert context.calls[-1]["region"] == "US-CA"
