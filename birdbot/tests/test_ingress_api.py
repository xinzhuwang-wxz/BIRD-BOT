"""Integration tests for the HTTP ingress (FastAPI via httpx ASGITransport + DB).

Skips without BIRDBOT_TEST_DATABASE_URL. Drives the app in-process — no real server.
"""
from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from birdbot.ingress.app import create_app
from birdbot.ingress.store import EventStore


def _client(app_db) -> AsyncClient:
    app = create_app(EventStore(app_db))
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


@pytest.mark.asyncio
async def test_post_event_returns_202_with_job_and_status_url(app_db):
    async with _client(app_db) as client:
        resp = await client.post(
            "/v0/events",
            json={
                "tenant_id": "A",
                "device_id": "d1",
                "event_id": "e1",
                "media": ["https://cdn/i.jpg"],
            },
        )
    assert resp.status_code == 202
    body = resp.json()
    assert body["status"] == "queued"
    assert body["job_id"]
    assert body["status_url"] == f"/v0/jobs/{body['job_id']}"


@pytest.mark.asyncio
async def test_duplicate_post_returns_same_job(app_db):
    payload = {"tenant_id": "A", "device_id": "d1", "event_id": "e1"}
    async with _client(app_db) as client:
        r1 = await client.post("/v0/events", json=payload)
        r2 = await client.post("/v0/events", json=payload)
    assert r1.json()["job_id"] == r2.json()["job_id"]
    assert r2.json()["duplicate"] is True


@pytest.mark.asyncio
async def test_missing_required_field_is_422(app_db):
    async with _client(app_db) as client:
        resp = await client.post(
            "/v0/events", json={"tenant_id": "A", "device_id": "d1"}  # no event_id
        )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_status_url_is_queryable(app_db):
    async with _client(app_db) as client:
        post = await client.post(
            "/v0/events",
            json={"tenant_id": "A", "device_id": "d1", "event_id": "e1"},
        )
        status_url = post.json()["status_url"]
        got = await client.get(status_url, headers={"X-Tenant-Id": "A"})
    assert got.status_code == 200
    assert got.json()["status"] == "queued"


@pytest.mark.asyncio
async def test_status_is_isolated_across_tenants(app_db):
    """Tenant B cannot read tenant A's job status (RLS extends to the HTTP layer)."""
    async with _client(app_db) as client:
        post = await client.post(
            "/v0/events",
            json={"tenant_id": "A", "device_id": "d1", "event_id": "e1"},
        )
        status_url = post.json()["status_url"]
        got = await client.get(status_url, headers={"X-Tenant-Id": "B"})
    assert got.status_code == 404
