"""Real HTTP ContextSource adapters (S20): iNaturalist + eBird.

Each derives per-species local frequency from its provider's response shape. The API key
lives here and is sent as a header — never handed to tenants/devices. eBird stays blocked
for commercial use until Cornell authorization (ADR-0005), enforced upstream by
BirdContextService's source × use × authorization matrix; this adapter just implements the
call.
"""
from __future__ import annotations

from collections.abc import Mapping

import httpx


def _normalize(counts: dict[str, int]) -> dict[str, float]:
    total = sum(counts.values()) or 1
    return {species: count / total for species, count in counts.items()}


class INatSource:
    """iNaturalist public records: GET observations -> results[].taxon.name."""

    name = "inaturalist"

    def __init__(self, client: httpx.AsyncClient, *, path: str = "/v1/observations") -> None:
        self._client = client
        self._path = path

    async def frequencies(self, *, region: str, date: str) -> Mapping[str, float]:
        response = await self._client.get(self._path, params={"place_id": region, "d1": date})
        response.raise_for_status()
        counts: dict[str, int] = {}
        for obs in response.json().get("results", []):
            name = (obs.get("taxon") or {}).get("name")
            if name:
                counts[name] = counts.get(name, 0) + 1
        return _normalize(counts)


class EbirdSource:
    """eBird recent observations: GET .../obs/{region}/recent -> list[].sciName.

    Key held here, sent as the X-eBirdApiToken header. Gated for commercial use upstream
    (ADR-0005); this adapter only performs the call.
    """

    name = "ebird"

    def __init__(
        self,
        client: httpx.AsyncClient,
        *,
        api_key: str,
        path_template: str = "/v2/data/obs/{region}/recent",
    ) -> None:
        self._client = client
        self._api_key = api_key
        self._path_template = path_template

    async def frequencies(self, *, region: str, date: str) -> Mapping[str, float]:
        response = await self._client.get(
            self._path_template.format(region=region),
            headers={"X-eBirdApiToken": self._api_key},
        )
        response.raise_for_status()
        counts: dict[str, int] = {}
        for obs in response.json():  # eBird returns a JSON list
            sci = obs.get("sciName")
            if sci:
                counts[sci] = counts.get(sci, 0) + 1
        return _normalize(counts)
