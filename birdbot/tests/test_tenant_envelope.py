"""Unit tests for the tenant envelope (no DB required).

The envelope is the immutable tenant identity threaded through deterministic
components; here we pin only its observable contract — the session_key encoding that
the agent facade consumes — not its internals.
"""
from __future__ import annotations

import pytest

from birdbot.tenant.context import TenantEnvelope


def test_session_key_encodes_tenant_user_device():
    env = TenantEnvelope(tenant_id="t1", user_id="u1", device_id="d1")
    assert env.session_key == "tenant:t1:user:u1:device:d1"


def test_session_key_uses_placeholder_when_user_or_device_absent():
    env = TenantEnvelope(tenant_id="t1")
    assert env.session_key == "tenant:t1:user:-:device:-"


def test_tenant_id_is_required():
    with pytest.raises(ValueError):
        TenantEnvelope(tenant_id="")


def test_envelope_is_immutable():
    env = TenantEnvelope(tenant_id="t1")
    with pytest.raises(Exception):
        env.tenant_id = "t2"  # type: ignore[misc]
