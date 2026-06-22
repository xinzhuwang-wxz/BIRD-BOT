"""Record/replay httpx transport for OpenAI-compatible providers (S14).

Inject into ``httpx.AsyncClient(transport=...)`` (which an OpenAI SDK client wraps).
- mode="record": call the real transport, persist {status, json} keyed by the request
  (method + url + body hash), and return it.
- mode="replay": return the recorded response; if none is recorded, raise loudly — it
  NEVER silently hits the network or needs a key.

Assumes JSON responses (LLM chat completions), which is all the deep stage / Nature Chat
need.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import httpx


def _request_key(request: httpx.Request) -> str:
    body = request.content or b""
    raw = f"{request.method}|{request.url}|{hashlib.sha256(body).hexdigest()}"
    return hashlib.sha256(raw.encode()).hexdigest()


class RecordReplayTransport(httpx.AsyncBaseTransport):
    def __init__(
        self,
        cassette_path: str | Path,
        *,
        mode: str = "replay",
        real_transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        if mode not in ("record", "replay"):
            raise ValueError("mode must be 'record' or 'replay'")
        if mode == "record" and real_transport is None:
            raise ValueError("record mode requires a real_transport")
        self._path = Path(cassette_path)
        self._mode = mode
        self._real = real_transport
        self._cassette: dict[str, dict] = (
            json.loads(self._path.read_text()) if self._path.exists() else {}
        )

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        key = _request_key(request)

        if self._mode == "replay":
            entry = self._cassette.get(key)
            if entry is None:
                raise RuntimeError(
                    f"no recorded response for {request.method} {request.url} "
                    f"(key={key[:12]}…); refusing to hit the network in replay mode"
                )
            return httpx.Response(entry["status"], json=entry["json"], request=request)

        assert self._real is not None  # guaranteed by __init__
        response = await self._real.handle_async_request(request)
        await response.aread()
        self._cassette[key] = {
            "status": response.status_code,
            "json": json.loads(response.content),
        }
        self._path.write_text(json.dumps(self._cassette, indent=2, ensure_ascii=False))
        return httpx.Response(
            response.status_code, json=self._cassette[key]["json"], request=request
        )
