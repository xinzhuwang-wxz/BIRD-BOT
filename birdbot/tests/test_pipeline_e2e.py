"""End-to-end main line (S15): POST -> 202 + fast snapshot -> advance deep -> Story
persisted + callback relayed. Needs DB; skips without DSN.

Uses a fake StoryLLM (the real-LLM vision path is covered by S12 + S14 record/replay), so
this verifies the orchestration wiring across every layer."""
from __future__ import annotations

import json

import pytest
from httpx import ASGITransport, AsyncClient

from birdbot.ingress.app import create_app
from birdbot.ingress.schema import BirdEvent
from birdbot.ingress.store import EventStore
from birdbot.pipeline.orchestrate import FastStageIngest, advance_deep
from birdbot.recognition.adapter import RecognitionAdapter
from birdbot.recognition.frame_scorer import FrameScorer
from birdbot.workflow.outbox import Outbox, relay
from birdbot.workflow.runtime import WorkflowRuntime

_STORY = {"behavior": "feeding", "rarity_narrative": "common", "story": "A robin fed."}


class _FakeStoryLLM:
    async def generate(self, *, prompt, frames, envelope, region="US"):
        self.frames = frames
        return _STORY


@pytest.mark.asyncio
async def test_ingress_to_deep_stage_end_to_end(app_db, admin_conn):
    ingest = FastStageIngest(
        EventStore(app_db), RecognitionAdapter(accept_threshold=0.5, margin=0.05), FrameScorer()
    )
    app = create_app(ingest)

    # 1. submit -> 202 + fast-stage snapshot landed
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as client:
        resp = await client.post(
            "/v0/events",
            json={
                "tenant_id": "A",
                "device_id": "d1",
                "event_id": "e1",
                "media": ["https://cdn/a.jpg"],
                "top_k": [{"label": "robin", "score": 0.9}],
            },
        )
    assert resp.status_code == 202
    assert resp.json()["job_id"]

    async with app_db.tenant_scope("A") as conn:
        payload = json.loads(await conn.fetchval("SELECT payload FROM events WHERE event_id = 'e1'"))
    assert payload["fast_stage"]["best_frame"] == "https://cdn/a.jpg"
    assert payload["fast_stage"]["candidates"][0] == ["robin", pytest.approx(1.0)]

    # 2. advance deep stage -> Story persisted (done) + callback enqueued
    fake_llm = _FakeStoryLLM()
    story = await advance_deep(
        db=app_db,
        runtime=WorkflowRuntime(app_db),
        outbox=Outbox(app_db),
        story_llm=fake_llm,
        tenant_id="A",
        device_id="d1",
        event_id="e1",
        region="US-CA",
    )
    assert story == _STORY
    assert fake_llm.frames == ["https://cdn/a.jpg"]  # best frame fed into deep stage

    async with app_db.tenant_scope("A") as conn:
        status = await conn.fetchval("SELECT status FROM events WHERE event_id = 'e1'")
    assert status == "done"

    # 3. callback is deliverable via the outbox relay
    delivered = []

    async def deliver(msg):
        delivered.append(msg)

    assert await relay(admin_conn, deliver) == 1
    assert delivered[0]["payload"]["story"] == _STORY
    assert delivered[0]["payload"]["workflow_id"] == "A:d1:e1"


@pytest.mark.asyncio
async def test_advance_deep_weaves_local_rarity_from_context_service(app_db):
    """G2: advance_deep calls the Bird Context Service (commercial=True) and weaves the
    local rarity labels into the Story prompt — no longer the hardcoded empty rarity."""
    from birdbot.context.models import BirdContext
    from birdbot.pipeline.orchestrate import advance_deep

    store = EventStore(app_db)
    await store.accept(
        BirdEvent(tenant_id="A", device_id="d1", event_id="e2",
                  top_k=[{"label": "robin", "score": 0.9}])
    )
    await store.attach_fast_snapshot(
        tenant_id="A", device_id="d1", event_id="e2",
        snapshot={"candidates": [["robin", 0.9]], "best_frame": None},
    )

    class _FakeContext:
        async def get_context(self, *, region, date, commercial):
            assert commercial is True  # paid path -> eBird/iNat intercepted pre-license (ADR-0005)
            return BirdContext(
                region=region, date=date, frequencies={"robin": 0.01},
                labels={"robin": "rare"}, source="taxonomy", attribution="src",
                degraded=False, diagnostics={},
            )

    captured: dict = {}

    class _CaptureStoryLLM:
        async def generate(self, *, prompt, frames, envelope, region="US"):
            captured["prompt"] = prompt
            return {"behavior": "feeding", "rarity_narrative": "x", "story": "y"}

    await advance_deep(
        db=app_db, runtime=WorkflowRuntime(app_db), outbox=Outbox(app_db),
        story_llm=_CaptureStoryLLM(), tenant_id="A", device_id="d1", event_id="e2",
        region="US-CA", context_service=_FakeContext(),
    )

    assert "robin" in captured["prompt"] and "rare" in captured["prompt"]  # rarity woven in
