"""Composition root (ADR-0014): assemble the deployable BirdBot app.

The single place that knows concrete adapters — Database, Model Router, LLMGateway
(telemetry / alert / quota), the deep-stage StoryLLM, FastStageIngest, the HTTP ingress, and
the outbox relay worker + HTTP delivery. Everything else sees only seams. Wiring is explicit
(inject components) so it is testable; thin ``*_from_env`` helpers can layer on top.

``Assembly`` is what a process entrypoint runs: serve ``app`` (ingress), start
``relay_worker`` (callback delivery), and call ``advance`` to drive the async deep stage.
"""
from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from birdbot.chat.handler import NatureChatHandler
from birdbot.deep.llm import build_story_llm
from birdbot.ingress.app import create_app
from birdbot.ingress.store import EventStore
from birdbot.recognition.adapter import RecognitionAdapter
from birdbot.recognition.frame_scorer import FrameScorer
from birdbot.router.router import ModelRouter
from birdbot.runtime.gateway import LLMGateway
from birdbot.workflow.deliver import HttpDeliver
from birdbot.workflow.worker import RelayWorker, make_deep_sweep, make_outbox_sweep


@dataclass(frozen=True)
class Assembly:
    app: Any  # FastAPI ingress app (mounts /v0/events + /v0/chat)
    gateway: LLMGateway
    story_llm: Any  # GatewayStoryLLM
    chat: Any  # NatureChatHandler (open interaction layer)
    relay_worker: RelayWorker  # callback delivery (outbox sweep)
    deep_worker: RelayWorker  # fast->deep auto-trigger (queued-events sweep)
    advance: Callable[..., Awaitable[dict[str, Any]]]  # drive one deep stage manually

    async def start(self) -> None:
        """Start the background workers — a process entrypoint calls this after serving app."""
        await self.relay_worker.start()
        await self.deep_worker.start()

    async def stop(self) -> None:
        await self.relay_worker.stop()
        await self.deep_worker.stop()


def assemble(
    *,
    db: Any,
    owner_dsn: str,
    registry: Any,
    completion: Callable[..., Awaitable[Any]],
    telemetry: Any,
    alerts: Any,
    quota: Any,
    webhook_url: str,
    http_client: Any,
    context_service: Any = None,
    relay_interval: float = 5.0,
) -> Assembly:
    """Wire the governed app from explicit components (the deploy env supplies them)."""
    from birdbot.pipeline.orchestrate import FastStageIngest, advance_deep
    from birdbot.workflow.outbox import Outbox
    from birdbot.workflow.runtime import WorkflowRuntime

    gateway = LLMGateway(
        router=ModelRouter(registry), telemetry=telemetry, alerts=alerts,
        quota=quota, completion=completion,
    )
    story_llm = build_story_llm(gateway=gateway)

    ingest = FastStageIngest(EventStore(db), RecognitionAdapter(), FrameScorer())
    chat = NatureChatHandler(gateway=gateway, alerts=alerts, db=db, context_service=context_service)
    app = create_app(ingest, chat=chat)

    runtime = WorkflowRuntime(db)
    outbox = Outbox(db)
    deliver = HttpDeliver(webhook_url=webhook_url, client=http_client)
    relay_worker = RelayWorker(
        sweep=make_outbox_sweep(owner_dsn=owner_dsn, deliver=deliver), interval=relay_interval
    )

    async def advance(*, tenant_id: str, device_id: str, event_id: str, region: str) -> dict[str, Any]:
        return await advance_deep(
            db=db, runtime=runtime, outbox=outbox, story_llm=story_llm,
            tenant_id=tenant_id, device_id=device_id, event_id=event_id, region=region,
            context_service=context_service,
        )

    deep_worker = RelayWorker(
        sweep=make_deep_sweep(owner_dsn=owner_dsn, advance=advance), interval=relay_interval
    )

    return Assembly(app=app, gateway=gateway, story_llm=story_llm, chat=chat,
                    relay_worker=relay_worker, deep_worker=deep_worker, advance=advance)
