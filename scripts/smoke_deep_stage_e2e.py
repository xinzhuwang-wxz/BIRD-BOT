"""Live end-to-end deep stage: real Doubao (vision) through run_deep_stage -> Postgres +
outbox + relay.

Needs LLM_API_KEY + BIRDBOT_TEST_DATABASE_URL + BIRD_IMAGE_PATH. Routes the model via the
Model Router (Doubao registered as deep-reasoning, CN), calls vision, enforces the Story
schema, persists the story, enqueues the callback, and relays it. Uses the admin
connection for brevity (RLS itself is covered by #3). Key/image from env; no key on disk.
Doubao is CN-residency — dev smoke only (ADR-0007).

    LLM_API_KEY=ark-... LLM_BASE_URL=https://ark.cn-beijing.volces.com/api/v3 \
        LLM_MODEL=doubao-seed-2-0-pro-260215 \
        BIRDBOT_TEST_DATABASE_URL=postgresql://postgres:postgres@localhost:5433/birdbot_test \
        BIRD_IMAGE_PATH=/tmp/birdbot_blue_tit.jpg \
        python scripts/smoke_deep_stage_e2e.py
"""
from __future__ import annotations

import asyncio
import base64
import json
import os
from pathlib import Path


async def main() -> None:
    api_key = os.environ.get("LLM_API_KEY")
    dsn = os.environ.get("BIRDBOT_TEST_DATABASE_URL")
    image_path = os.environ.get("BIRD_IMAGE_PATH")
    if not (api_key and dsn and image_path):
        raise SystemExit("set LLM_API_KEY, BIRDBOT_TEST_DATABASE_URL, BIRD_IMAGE_PATH")
    api_base = os.environ.get("LLM_BASE_URL", "https://ark.cn-beijing.volces.com/api/v3")
    model = os.environ.get("LLM_MODEL", "doubao-seed-2-0-pro-260215")

    import asyncpg
    from birdbot.db.migrations import apply_migrations
    from birdbot.db.pool import Database
    from birdbot.deep.llm import build_story_llm
    from birdbot.deep.workflow import run_deep_stage
    from birdbot.observability.alerts import ListAlertSink
    from birdbot.observability.telemetry import ListTelemetrySink
    from birdbot.runtime.gateway import LLMGateway
    from birdbot.ingress.schema import BirdEvent
    from birdbot.ingress.store import EventStore
    from birdbot.router.registry import Capability, CapabilityRegistry, ModelEntry
    from birdbot.router.router import ModelRouter
    from birdbot.workflow.outbox import Outbox, relay
    from birdbot.workflow.runtime import WorkflowRuntime
    import litellm

    admin = await asyncpg.connect(dsn)
    try:
        # The migration GRANTs to birdbot_app; the deploy env (here the smoke) creates it.
        await admin.execute(
            "DO $$ BEGIN IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'birdbot_app') "
            "THEN CREATE ROLE birdbot_app LOGIN PASSWORD 'birdbot_test_pw'; END IF; END $$;"
        )
        await apply_migrations(admin)
        await admin.execute("TRUNCATE TABLE events, workflow_steps, outbox")
    finally:
        await admin.close()

    db = await Database.connect(dsn)  # superuser bypasses RLS (e2e brevity; RLS in #3)
    try:
        await EventStore(db).accept(BirdEvent(tenant_id="A", device_id="d1", event_id="e1"))

        registry = CapabilityRegistry(
            [
                ModelEntry(
                    logical_name="deep-reasoning",
                    backend="openai_compat",
                    model=model,
                    capabilities=frozenset({Capability.VISION, Capability.STRUCTURED_OUTPUT}),
                    context_window=128_000,
                    pricing_per_mtok=1.0,
                    residency_region="CN",
                    compliance_tags=frozenset(),
                )
            ]
        )
        router = ModelRouter(registry)

        async def completion(*, model, messages, **kwargs):  # LiteLLM OpenAI-compat path
            return await litellm.acompletion(
                model=f"openai/{model}", messages=messages,
                api_base=api_base, api_key=api_key, **kwargs,
            )

        class _AllowQuota:  # smoke: always allow (production uses RedisQuotaLimiter)
            async def try_acquire(self, key):
                return True

            async def release(self, key):
                pass

        gateway = LLMGateway(
            router=router,
            telemetry=ListTelemetrySink(),
            alerts=ListAlertSink(),
            quota=_AllowQuota(),
            completion=completion,
        )
        story_llm = build_story_llm(gateway=gateway)

        data_url = "data:image/jpeg;base64," + base64.b64encode(
            Path(image_path).read_bytes()
        ).decode()
        snapshot = {
            "candidates": [["Cyanistes caeruleus", 0.94]],
            "rarity": {"Cyanistes caeruleus": "common"},
            "region": "US-CA",
            "frames": [data_url],
        }

        story = await run_deep_stage(
            db=db,
            runtime=WorkflowRuntime(db),
            outbox=Outbox(db),
            story_llm=story_llm,
            tenant_id="A",
            device_id="d1",
            event_id="e1",
            snapshot=snapshot,
            user_region="US",
        )

        async with db.tenant_scope("A") as conn:
            status = await conn.fetchval("SELECT status FROM events WHERE event_id = 'e1'")
            enqueued = await conn.fetchval("SELECT count(*) FROM outbox WHERE topic = 'callback'")

        delivered: list = []
        admin2 = await asyncpg.connect(dsn)
        try:

            async def deliver(msg):
                delivered.append(msg)

            relayed = await relay(admin2, deliver)
        finally:
            await admin2.close()
    finally:
        await db.close()

    print(f"=== run_deep_stage via {model} ===")
    print(f"event status: {status} | callbacks enqueued: {enqueued} | relayed: {relayed}")
    print("=== STORY ===")
    print(json.dumps(story, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
