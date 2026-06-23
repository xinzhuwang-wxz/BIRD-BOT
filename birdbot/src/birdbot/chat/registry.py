"""Per-request tenant-scoped tool registry (方案 B9 / §176).

Builds a ToolRegistry whose tools are bound to this request's TenantEnvelope + region, so
tenant/device/region are deterministic and never LLM-settable. One registry per request —
the deterministic context flows through construction, not through the model.
"""
from __future__ import annotations

from birdbot.chat.tools import (
    BirdContextTool,
    DeviceHistoryTool,
    RarityLookup,
    VisitsLookup,
)
from birdbot.runtime.registry import ToolRegistry
from birdbot.tenant.context import TenantEnvelope


def build_nature_chat_registry(
    *,
    envelope: TenantEnvelope,
    region: str,
    visits: VisitsLookup,
    rarity: RarityLookup,
) -> ToolRegistry:
    """A tool registry scoped to one request: device bound from the envelope, region bound
    from the (post-degradation) device location. Neither is exposed to the LLM. ``visits`` /
    ``rarity`` are async lookups (production: events history / Bird Context Service; tests:
    dict_visits / dict_rarity)."""
    registry = ToolRegistry()
    registry.register(DeviceHistoryTool(visits, device_id=envelope.device_id))
    registry.register(BirdContextTool(rarity, region=region))
    return registry
