"""run_deep_stage: advance one BirdEvent through the deep stage.

A single re-entrant workflow step (#5): route the model (#6), call the StoryLLM with
<=8 curated frames + evidence, enforce the output schema (hard contract, in code), then
persist the story and enqueue the callback in the SAME transaction (#5 outbox). The whole
step is journaled, so a resume replays the recorded story without re-calling the LLM or
re-enqueuing.
"""
from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from birdbot.db.pool import Database
from birdbot.deep.story import MAX_FRAMES, STORY_SCHEMA, StoryLLM, build_story_prompt
from birdbot.router.validate import validate_structured_output
from birdbot.tenant.context import TenantEnvelope
from birdbot.workflow.outbox import Outbox
from birdbot.workflow.runtime import WorkflowRuntime


async def run_deep_stage(
    *,
    db: Database,
    runtime: WorkflowRuntime,
    outbox: Outbox,
    story_llm: StoryLLM,
    tenant_id: str,
    device_id: str,
    event_id: str,
    snapshot: Mapping[str, Any],
    user_region: str = "US",
    callback_topic: str = "callback",
) -> dict[str, Any]:
    workflow_id = f"{tenant_id}:{device_id}:{event_id}"

    async def story_step() -> dict[str, Any]:
        frames = list(snapshot.get("frames", []))[:MAX_FRAMES]
        story = await story_llm.generate(
            prompt=build_story_prompt(snapshot),
            frames=frames,
            envelope=TenantEnvelope(tenant_id=tenant_id, device_id=device_id),
            region=user_region,
        )
        # Hard contract enforced in code (not the Skill).
        errors = validate_structured_output(story, STORY_SCHEMA)
        if errors:
            raise ValueError(f"deep-stage story violates schema: {errors}")

        # Persist + enqueue callback atomically (same transaction).
        async with db.tenant_scope(tenant_id) as conn:
            await conn.execute(
                """
                UPDATE events SET status = 'done', payload = payload || $3::jsonb
                WHERE device_id = $1 AND event_id = $2
                """,
                device_id,
                event_id,
                json.dumps({"story": story}),
            )
            await outbox.enqueue(
                conn,
                tenant_id=tenant_id,
                topic=callback_topic,
                payload={"workflow_id": workflow_id, "story": story,
                         "attribution": snapshot.get("attribution")},
                dedupe_key=workflow_id,
            )
        return story

    return await runtime.run_step(
        tenant_id=tenant_id,
        workflow_id=workflow_id,
        step_name="deep_story",
        fn=story_step,
    )
