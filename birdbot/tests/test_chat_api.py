"""Nature Chat HTTP entrypoint: /v0/chat + NatureChatHandler (open interaction layer).

The handler drives the governed AgentRuntime over a tenant-scoped tool registry; the endpoint
is mounted only when a chat handler is provided. No DB / no key — gateway + handler are faked.
"""
from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from birdbot.chat.handler import NatureChatHandler
from birdbot.ingress.app import create_app
from birdbot.observability.alerts import ListAlertSink
from birdbot.runtime.gateway import GatewayResult
from birdbot.tenant.context import TenantEnvelope


class _FakeGateway:
    def __init__(self):
        self.seen: list[dict] = []

    async def complete(self, *, envelope, logical_model, messages, skill, region="US", **kw):
        self.seen.append({"envelope": envelope, "skill": skill, "region": region})
        return GatewayResult(raw={"choices": [{"message": {"content": "Yes — a regular!"}}]},
                             provider="x", tokens=1, cost_usd=0.0, latency_ms=1.0)


@pytest.mark.asyncio
async def test_handler_runs_governed_runtime_with_bound_context():
    gw = _FakeGateway()
    handler = NatureChatHandler(gateway=gw, alerts=ListAlertSink(),
                                history={"blue tit": {"visits_30d": 8}},
                                rarity={"blue tit": "common"})
    envelope = TenantEnvelope(tenant_id="A", device_id="d1")

    reply = await handler.handle(envelope=envelope, prompt="is the blue tit a regular?",
                                 region="US-CA")

    assert reply == "Yes — a regular!"
    assert gw.seen[0]["skill"] == "chat"  # governed under the chat skill quota bucket
    assert gw.seen[0]["region"] == "US-CA"  # deterministic region flows through
    assert gw.seen[0]["envelope"].tenant_id == "A"


@pytest.mark.asyncio
async def test_chat_endpoint_returns_reply():
    class _FakeChat:
        async def handle(self, *, envelope, prompt, region):
            return f"reply[{region}]: {prompt}"

    app = create_app(ingest=None, chat=_FakeChat())
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as client:
        resp = await client.post("/v0/chat", json={
            "tenant_id": "A", "device_id": "d1", "prompt": "hello", "region": "US-CA",
        })

    assert resp.status_code == 200
    assert resp.json()["reply"] == "reply[US-CA]: hello"


@pytest.mark.asyncio
async def test_chat_endpoint_not_mounted_without_handler():
    app = create_app(ingest=None)  # no chat handler -> /v0/chat is not mounted
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as client:
        resp = await client.post("/v0/chat", json={"tenant_id": "A", "prompt": "x"})
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_chat_endpoint_validates_body():
    class _FakeChat:
        async def handle(self, *, envelope, prompt, region):
            return "ok"

    app = create_app(ingest=None, chat=_FakeChat())
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as client:
        resp = await client.post("/v0/chat", json={"tenant_id": "A"})  # missing prompt
    assert resp.status_code == 422  # FastAPI rejects the bad body
