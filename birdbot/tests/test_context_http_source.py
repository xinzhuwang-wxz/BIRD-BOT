"""HTTP-backed ContextSource tested over a real httpx stack via MockTransport.

Confirms frequency parsing, that the API key is held in this layer (sent as a header,
never handed out), and that an error status raises (so the service degrades to it)."""
from __future__ import annotations

import httpx
import pytest

from birdbot.context.adapters import HttpContextSource


@pytest.mark.asyncio
async def test_parses_normalized_frequencies_and_holds_key_in_header():
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["token"] = request.headers.get("x-ebirdapitoken")
        return httpx.Response(
            200,
            json={"results": [{"species": "robin"}, {"species": "robin"}, {"species": "sparrow"}]},
        )

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport, base_url="https://api.test") as client:
        source = HttpContextSource(
            name="inaturalist", client=client, path="/v1/obs", api_key="secret-key"
        )
        freqs = await source.frequencies(region="US-CA", date="2026-06-22")

    assert freqs == {"robin": pytest.approx(2 / 3), "sparrow": pytest.approx(1 / 3)}
    assert captured["token"] == "secret-key"  # key held here, sent in header


@pytest.mark.asyncio
async def test_error_status_raises_for_service_to_degrade():
    transport = httpx.MockTransport(lambda request: httpx.Response(503))
    async with httpx.AsyncClient(transport=transport, base_url="https://api.test") as client:
        source = HttpContextSource(name="ebird", client=client, path="/obs")
        with pytest.raises(httpx.HTTPStatusError):
            await source.frequencies(region="R", date="D")
