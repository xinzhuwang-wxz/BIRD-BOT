"""The tenant envelope: immutable tenant identity for one request.

Resolved by the auth pipeline (later slice) and threaded through every deterministic
component. It derives the conversation session_key the agent facade consumes and is
the source of truth for the Postgres ``app.current_tenant`` setting (ADR-0004).
"""
from __future__ import annotations

from dataclasses import dataclass

_ABSENT = "-"


@dataclass(frozen=True, slots=True)
class TenantEnvelope:
    """Immutable ``(tenant, user, device)`` identity for one request."""

    tenant_id: str
    user_id: str | None = None
    device_id: str | None = None

    def __post_init__(self) -> None:
        if not self.tenant_id:
            raise ValueError("tenant_id is required and must be non-empty")

    @property
    def session_key(self) -> str:
        """Encode the tenant boundary as ``tenant:{tid}:user:{uid}:device:{did}``.

        Absent user/device collapse to a stable ``-`` placeholder so the key always
        carries the full boundary and stays parseable.
        """
        return (
            f"tenant:{self.tenant_id}"
            f":user:{self.user_id or _ABSENT}"
            f":device:{self.device_id or _ABSENT}"
        )
