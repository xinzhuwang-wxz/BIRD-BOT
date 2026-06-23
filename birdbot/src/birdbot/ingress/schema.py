"""BirdEvent v0 — the versioned event an IoT platform submits (ADR-0003).

The deep module A1 (parse/validate -> idempotency key -> serialize) starts here. v0
carries the identity triple used for the idempotency key (tenant+device+event_id),
optional media URLs, optional on-device Top-K, and a coarse location. Media is optional
so devices of differing richness all work (缺媒体可接受).
"""
from __future__ import annotations

from pydantic import BaseModel, Field

from birdbot.tenant.context import TenantEnvelope


class SpeciesCandidate(BaseModel):
    """One on-device Top-K detection candidate."""

    label: str = Field(min_length=1)
    score: float = Field(ge=0.0, le=1.0)


class CoarseLocation(BaseModel):
    """Coarse location as submitted. Persistence-side privacy degradation lives in
    privacy/location.py. ``region`` is the eBird region code (e.g. US-CA) the IoT platform
    supplies — BirdBot does not geocode lat/lon; the device/platform knows where it is."""

    lat: float | None = None
    lon: float | None = None
    grid: str | None = None
    region: str | None = None


class BirdEvent(BaseModel):
    """A single bird visit submitted by an IoT platform (v0)."""

    schema_version: str = "v0"
    tenant_id: str = Field(min_length=1)
    user_id: str | None = None
    device_id: str = Field(min_length=1)
    event_id: str = Field(min_length=1)
    media: list[str] = Field(default_factory=list)
    top_k: list[SpeciesCandidate] = Field(default_factory=list)
    location: CoarseLocation | None = None

    @property
    def envelope(self) -> TenantEnvelope:
        """The immutable tenant identity this event carries (v0: body-sourced)."""
        return TenantEnvelope(
            tenant_id=self.tenant_id, user_id=self.user_id, device_id=self.device_id
        )

    @property
    def session_key(self) -> str:
        return self.envelope.session_key


class ChatRequest(BaseModel):
    """One Nature Chat turn submitted to /v0/chat (open interaction layer)."""

    tenant_id: str = Field(min_length=1)
    user_id: str | None = None
    device_id: str | None = None
    prompt: str = Field(min_length=1)
    region: str = "US"  # eBird region code, supplied by the platform (never LLM-inferred)

    @property
    def envelope(self) -> TenantEnvelope:
        return TenantEnvelope(
            tenant_id=self.tenant_id, user_id=self.user_id, device_id=self.device_id
        )
