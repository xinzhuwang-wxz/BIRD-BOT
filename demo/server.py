"""The demo HTTP server: one DemoEngine behind three browser faces.

Run it:
    source .venv/bin/activate
    python -m demo.server          # then open http://127.0.0.1:8800

Static pages live in demo/static; the JSON API + the live SSE stream live here. There is no
build step and no external service — everything runs in-process.
"""
from __future__ import annotations

import asyncio
import json
import random
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles

from demo.engine import DemoEngine, fleet_public, scenarios_public
from demo.scenarios import DEVICES_BY_ID, FLEET

_STATIC = Path(__file__).parent / "static"

engine = DemoEngine()
app = FastAPI(title="BirdBot Product Showcase", version="0")


# --- catalog / config --------------------------------------------------------
@app.get("/api/fleet")
async def fleet() -> list[dict]:
    return fleet_public()


@app.get("/api/scenarios")
async def scenarios() -> list[dict]:
    return scenarios_public()


@app.get("/api/routing")
async def routing() -> list[dict]:
    return engine.routing_table()


# --- device simulator --------------------------------------------------------
@app.post("/api/sim/event")
async def sim_event(req: Request) -> dict:
    body = await req.json()
    if not body.get("scenario"):
        device = DEVICES_BY_ID.get(body.get("device_id", ""))
        if device is None:
            raise HTTPException(404, f"unknown device {body.get('device_id')!r}")
        body["scenario"] = random.choice(device.scenarios)
    try:
        return await engine.ingest_event(body)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@app.post("/api/sim/random")
async def sim_random() -> dict:
    device = random.choice(FLEET)
    return await engine.ingest_event(
        {"device_id": device.device_id, "scenario": random.choice(device.scenarios)}
    )


# --- end-user app ------------------------------------------------------------
@app.get("/api/observations")
async def observations(device_id: str, tenant_id: str | None = None) -> list[dict]:
    device = DEVICES_BY_ID.get(device_id)
    if device is None:
        raise HTTPException(404, f"unknown device {device_id!r}")
    return engine.observations(tenant_id or device.tenant_id, device_id)


@app.get("/api/digest")
async def digest(device_id: str, tenant_id: str | None = None) -> dict:
    device = DEVICES_BY_ID.get(device_id)
    if device is None:
        raise HTTPException(404, f"unknown device {device_id!r}")
    return engine.digest(tenant_id or device.tenant_id, device_id)


@app.post("/api/chat")
async def chat(req: Request) -> dict:
    body = await req.json()
    if not body.get("prompt"):
        raise HTTPException(400, "prompt is required")
    try:
        reply = await engine.chat(body)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return {"reply": reply}


# --- ops console -------------------------------------------------------------
@app.get("/api/metrics")
async def metrics() -> dict:
    return engine.metrics()


# --- live stream (powers every face) ----------------------------------------
@app.get("/api/events/stream")
async def stream(req: Request) -> StreamingResponse:
    async def gen():
        agen = engine.bus.subscribe()
        try:
            async for event in agen:
                if await req.is_disconnected():
                    break
                yield f"data: {json.dumps(event)}\n\n"
        except asyncio.CancelledError:
            pass
        finally:
            await agen.aclose()

    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


# --- static (must be mounted last so /api/* wins) ---------------------------
app.mount("/", StaticFiles(directory=str(_STATIC), html=True), name="static")


def main() -> None:
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8800, log_level="info")


if __name__ == "__main__":
    main()
