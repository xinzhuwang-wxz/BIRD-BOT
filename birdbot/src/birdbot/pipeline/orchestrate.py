"""Main-line orchestration (S15): ingress -> fast stage -> deep stage.

FastStageIngest is the synchronous 202 path: accept (idempotent) -> run the fast stage ->
land a candidate/best-frame snapshot on the event. advance_deep is the asynchronous path:
read the snapshot, run the deep stage (Model Router -> StoryLLM) via the Workflow Runtime,
persist the Story, and deliver the callback via the outbox.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from birdbot.ingress.schema import BirdEvent
from birdbot.ingress.store import AcceptResult, EventStore
from birdbot.pipeline.convert import candidates_from_topk, frames_from_media
from birdbot.recognition.adapter import RecognitionAdapter
from birdbot.recognition.fast_stage import run_fast_stage
from birdbot.recognition.frame_scorer import FrameScorer


def _utc_date() -> str:
    return datetime.now(timezone.utc).date().isoformat()


class FastStageIngest:
    """Accept a BirdEvent, run the fast stage, and land its snapshot — the 202 path."""

    def __init__(
        self,
        store: EventStore,
        adapter: RecognitionAdapter,
        frame_scorer: FrameScorer,
        *,
        temperature: float = 1.5,
    ) -> None:
        self._store = store
        self._adapter = adapter
        self._frame_scorer = frame_scorer
        self._temperature = temperature

    async def submit(self, event: BirdEvent) -> AcceptResult:
        result = await self._store.accept(event)
        if not result.duplicate:
            fast = run_fast_stage(
                raw_candidates=candidates_from_topk(event),
                frames=frames_from_media(event),
                adapter=self._adapter,
                frame_scorer=self._frame_scorer,
                temperature=self._temperature,
            )
            snapshot = {
                "candidates": [[c.label, c.score] for c in fast.candidates],
                "confidence": fast.confidence,
                "decision": fast.decision.action,
                "best_frame": fast.best_frame.frame_id if fast.best_frame else None,
            }
            await self._store.attach_fast_snapshot(
                tenant_id=event.tenant_id,
                device_id=event.device_id,
                event_id=event.event_id,
                snapshot=snapshot,
            )
        return result

    async def job_status(self, tenant_id: str, job_id: str) -> str | None:
        return await self._store.job_status(tenant_id, job_id)


async def advance_deep(
    *,
    db: Any,
    runtime: Any,
    outbox: Any,
    story_llm: Any,
    tenant_id: str,
    device_id: str,
    event_id: str,
    region: str,
    context_service: Any = None,
    date: str | None = None,
) -> dict[str, Any]:
    """Read the fast-stage snapshot and advance the deep stage to a persisted Story.

    region is supplied deterministically (device location, S13), never inferred by the LLM.
    Routing/governance live in the LLMGateway the story_llm holds (ADR-0014). When a
    context_service is provided, local rarity is fetched with commercial=True — so eBird/iNat
    are intercepted pre-license (ADR-0005) and degrade visibly — and woven into the Story.
    """
    from birdbot.context.rerank import make_geo_temporal_reranker
    from birdbot.deep.workflow import run_deep_stage
    from birdbot.recognition.types import ScoredCandidate

    async with db.tenant_scope(tenant_id) as conn:
        raw = await conn.fetchval(
            "SELECT payload FROM events WHERE device_id = $1 AND event_id = $2",
            device_id,
            event_id,
        )
    fast = json.loads(raw).get("fast_stage", {})
    candidates = fast.get("candidates", [])

    rarity: dict[str, Any] = {}
    attribution = None
    if context_service is not None:
        ctx = await context_service.get_context(
            region=region, date=date or _utc_date(), commercial=True
        )
        rarity = dict(ctx.labels)
        attribution = ctx.attribution
        # geo/temporal rerank by local frequency (G2b, ADR-0015): the deep stage reuses the
        # context it already fetched for rarity, so the fast stage stays synchronous.
        if candidates and ctx.frequencies:
            reranker = make_geo_temporal_reranker(ctx)
            reranked = reranker(
                [ScoredCandidate(label, score) for label, score in candidates], None
            )
            candidates = [[c.label, c.score] for c in reranked]

    snapshot = {
        "candidates": candidates,
        "frames": [fast["best_frame"]] if fast.get("best_frame") else [],
        "rarity": rarity,
        "region": region,
        "attribution": attribution,
    }
    return await run_deep_stage(
        db=db,
        runtime=runtime,
        outbox=outbox,
        story_llm=story_llm,
        tenant_id=tenant_id,
        device_id=device_id,
        event_id=event_id,
        snapshot=snapshot,
        user_region=region,
    )
