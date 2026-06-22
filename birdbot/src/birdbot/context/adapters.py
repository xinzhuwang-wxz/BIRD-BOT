"""HTTP-backed ContextSource adapters.

A thin source over an HTTP API (e.g. iNaturalist public records — the compliant
degraded baseline). The API key lives here and is sent as a header; it never leaves this
layer to a tenant/device (ADR-0005). Per-species local frequency is derived from the
observations response.

The eBird adapter is intentionally not wired into any paid path until Cornell
authorization lands (ADR-0005); this generic adapter covers the key-less / iNat baseline
and is the shape the eBird adapter will take.
"""
from __future__ import annotations

from collections.abc import Mapping

import httpx


class HttpContextSource:
    def __init__(
        self,
        *,
        name: str,
        client: httpx.AsyncClient,
        path: str,
        api_key: str | None = None,
        api_key_header: str = "X-eBirdApiToken",
    ) -> None:
        self.name = name
        self._client = client
        self._path = path
        self._api_key = api_key
        self._api_key_header = api_key_header

    async def frequencies(self, *, region: str, date: str) -> Mapping[str, float]:
        headers = {self._api_key_header: self._api_key} if self._api_key else {}
        response = await self._client.get(
            self._path, params={"region": region, "date": date}, headers=headers
        )
        response.raise_for_status()

        counts: dict[str, int] = {}
        for observation in response.json().get("results", []):
            species = observation.get("species")
            if species:
                counts[species] = counts.get(species, 0) + 1
        total = sum(counts.values()) or 1
        return {species: count / total for species, count in counts.items()}
