"""Integration tests for the deep stage (needs DB; skips without DSN).

Ties together WorkflowRuntime (#5), Outbox (#5), ModelRouter (#6), and a fake StoryLLM:
the LLM is routed via the Model Router, receives <=8 frames + structured evidence, the
hard output contract is enforced in code (not the Skill), the story is persisted, and a
callback is enqueued in the same transaction. Resuming replays without re-calling.
"""
from __future__ import annotations

import json

import pytest

from birdbot.deep.workflow import run_deep_stage
from birdbot.ingress.schema import BirdEvent
from birdbot.ingress.store import EventStore
from birdbot.router.registry import Capability, CapabilityRegistry, ModelEntry
from birdbot.router.router import ModelRouter
from birdbot.workflow.outbox import Outbox, relay
from birdbot.workflow.runtime import WorkflowRuntime

_STORY = {
    "behavior": "feeding",
    "rarity_narrative": "a common local visitor this season",
    "story": "A robin stopped by the feeder this morning.",
}


class FakeStoryLLM:
    def __init__(self, result):
        self._result = result
        self.calls = 0
        self.capture = {}

    async def generate(self, *, prompt, frames, schema, model):
        self.calls += 1
        self.capture = {"prompt": prompt, "frames": frames, "schema": schema, "model": model}
        return self._result


def _router():
    return ModelRouter(
        CapabilityRegistry(
            [
                ModelEntry(
                    logical_name="deep-reasoning",
                    backend="anthropic",
                    model="claude-opus-4-8",
                    capabilities=frozenset({Capability.STRUCTURED_OUTPUT, Capability.VISION}),
                    context_window=200_000,
                    pricing_per_mtok=15.0,
                    residency_region="US",
                    compliance_tags=frozenset({"dpf"}),
                )
            ]
        )
    )


async def _seed_event(app_db, *, device_id="d1", event_id="e1"):
    await EventStore(app_db).accept(
        BirdEvent(tenant_id="A", device_id=device_id, event_id=event_id)
    )


@pytest.mark.asyncio
async def test_deep_stage_persists_story_and_enqueues_callback(app_db):
    await _seed_event(app_db)
    llm = FakeStoryLLM(_STORY)

    story = await run_deep_stage(
        db=app_db,
        runtime=WorkflowRuntime(app_db),
        outbox=Outbox(app_db),
        router=_router(),
        story_llm=llm,
        tenant_id="A",
        device_id="d1",
        event_id="e1",
        snapshot={"candidates": [["robin", 0.9]], "frames": ["f1.jpg"], "rarity": {"robin": "common"}},
    )

    assert story["story"] == _STORY["story"]
    assert llm.capture["model"] == "claude-opus-4-8"  # routed via Model Router
    async with app_db.tenant_scope("A") as conn:
        row = await conn.fetchrow("SELECT status, payload FROM events WHERE event_id = 'e1'")
        assert row["status"] == "done"
        assert json.loads(row["payload"])["story"]["behavior"] == "feeding"
        assert await conn.fetchval("SELECT count(*) FROM outbox WHERE topic = 'callback'") == 1


@pytest.mark.asyncio
async def test_deep_stage_limits_frames_to_eight(app_db):
    await _seed_event(app_db)
    llm = FakeStoryLLM(_STORY)
    await run_deep_stage(
        db=app_db, runtime=WorkflowRuntime(app_db), outbox=Outbox(app_db), router=_router(),
        story_llm=llm, tenant_id="A", device_id="d1", event_id="e1",
        snapshot={"frames": [f"f{i}.jpg" for i in range(20)]},
    )
    assert len(llm.capture["frames"]) == 8


@pytest.mark.asyncio
async def test_hard_contract_rejects_invalid_story_schema(app_db):
    await _seed_event(app_db)
    bad_llm = FakeStoryLLM({"behavior": "feeding"})  # missing rarity_narrative / story
    with pytest.raises(ValueError):
        await run_deep_stage(
            db=app_db, runtime=WorkflowRuntime(app_db), outbox=Outbox(app_db), router=_router(),
            story_llm=bad_llm, tenant_id="A", device_id="d1", event_id="e1", snapshot={"frames": []},
        )


@pytest.mark.asyncio
async def test_deep_stage_resumes_without_recalling_llm(app_db):
    await _seed_event(app_db)
    llm = FakeStoryLLM(_STORY)
    args = dict(
        db=app_db, runtime=WorkflowRuntime(app_db), outbox=Outbox(app_db), router=_router(),
        story_llm=llm, tenant_id="A", device_id="d1", event_id="e1", snapshot={"frames": []},
    )
    await run_deep_stage(**args)
    await run_deep_stage(**args)  # resume
    assert llm.calls == 1  # story step replayed, LLM not called again


@pytest.mark.asyncio
async def test_callback_is_deliverable_via_outbox_relay(app_db, admin_conn):
    await _seed_event(app_db)
    await run_deep_stage(
        db=app_db, runtime=WorkflowRuntime(app_db), outbox=Outbox(app_db), router=_router(),
        story_llm=FakeStoryLLM(_STORY), tenant_id="A", device_id="d1", event_id="e1",
        snapshot={"frames": []},
    )
    delivered = []

    async def deliver(msg):
        delivered.append(msg)

    assert await relay(admin_conn, deliver) == 1
    assert delivered[0]["payload"]["story"]["story"] == _STORY["story"]
