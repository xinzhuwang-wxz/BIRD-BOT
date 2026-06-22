"""FastAPI ingress app (ADR-0010).

``create_app(store)`` is a factory so the EventStore (and its tenant-scoped DB) can be
injected — handy for tests and for future per-deployment wiring. POST validates the
BirdEvent (FastAPI -> 422 on bad bodies), lands it, and returns a 202 acceptance
receipt with a status_url; GET reports job status within the requesting tenant.
"""
from __future__ import annotations

from fastapi import FastAPI, Header, HTTPException

from birdbot.ingress.schema import BirdEvent
from birdbot.ingress.store import EventStore


def create_app(store: EventStore) -> FastAPI:
    app = FastAPI(title="BirdBot Ingress", version="0")

    @app.post("/v0/events", status_code=202)
    async def post_event(event: BirdEvent) -> dict:
        result = await store.accept(event)
        return {
            "job_id": str(result.job_id),
            "status": result.status,
            "status_url": f"/v0/jobs/{result.job_id}",
            "duplicate": result.duplicate,
        }

    @app.get("/v0/jobs/{job_id}")
    async def get_job(
        job_id: str,
        # v0: tenant rides in a header; the auth pipeline (B9) will replace this with a
        # verified identity. Never trusted as a security boundary until then (ADR-0010).
        x_tenant_id: str = Header(...),
    ) -> dict:
        status = await store.job_status(x_tenant_id, job_id)
        if status is None:
            raise HTTPException(status_code=404, detail="job not found")
        return {"job_id": job_id, "status": status}

    return app
