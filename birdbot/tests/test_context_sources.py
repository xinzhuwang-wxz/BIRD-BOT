"""Real eBird/iNat HTTP source adapters (S20), tested over httpx MockTransport.

iNat parses results[].taxon.name; eBird parses a recent-observations list[].sciName and
holds the API key in a header (never handed out). eBird stays blocked for commercial use
until the Cornell license lands (ADR-0005), enforced by BirdContextService."""
from __future__ import annotations

import httpx
import pytest

from birdbot.context.models import SourceMode
from birdbot.context.service import BirdContextService
from birdbot.context.sources import EbirdSource, INatSource


@pytest.mark.asyncio
async def test_inat_source_parses_taxon_frequencies():
    def handler(req):
        return httpx.Response(
            200,
            json={"results": [
                {"taxon": {"name": "Turdus migratorius"}},
                {"taxon": {"name": "Turdus migratorius"}},
                {"taxon": {"name": "Passer domesticus"}},
            ]},
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url="https://api.inaturalist.org")
    freqs = await INatSource(client).frequencies(region="123", date="2026-06-23")
    assert freqs == {
        "Turdus migratorius": pytest.approx(2 / 3),
        "Passer domesticus": pytest.approx(1 / 3),
    }


@pytest.mark.asyncio
async def test_ebird_source_parses_list_and_holds_key_in_header():
    captured = {}

    def handler(req):
        captured["token"] = req.headers.get("x-ebirdapitoken")
        return httpx.Response(
            200,
            json=[
                {"sciName": "Cyanistes caeruleus"},
                {"sciName": "Cyanistes caeruleus"},
                {"sciName": "Erithacus rubecula"},
            ],
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url="https://api.ebird.org")
    freqs = await EbirdSource(client, api_key="secret").frequencies(region="US-CA", date="2026-06-23")
    assert freqs["Cyanistes caeruleus"] == pytest.approx(2 / 3)
    assert captured["token"] == "secret"  # key held here, sent in header


@pytest.mark.asyncio
async def test_ebird_blocked_for_commercial_use_via_service():
    ebird = EbirdSource(
        httpx.AsyncClient(
            transport=httpx.MockTransport(lambda r: httpx.Response(200, json=[{"sciName": "x"}])),
            base_url="https://api.ebird.org",
        ),
        api_key="k",
    )
    svc = BirdContextService(sources={"ebird": ebird})
    ctx = await svc.get_context(
        region="US-CA", date="2026-06-23", mode=SourceMode.EBIRD_ONLY, commercial=True
    )
    assert ctx.source is None  # pre-license: eBird does not enter a paid path (ADR-0005)
    assert ctx.degraded is True
