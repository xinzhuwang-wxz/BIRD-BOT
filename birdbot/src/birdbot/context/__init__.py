"""Bird Context Service (A4, ADR-0005): the single, governed outlet for local bird
context (eBird / iNaturalist / taxonomy).

Holds the one API key (never handed to tenants/devices), caches and rate-limits to stay
well under eBird's 1000 req/day, applies a source × use × authorization matrix with
commercial-use interception, forces attribution, and coarse-grids sensitive species.
Data-source mode is explicit (auto | ebird-only | non-ebird-only); the active mode and
any degradation / circuit-break / quota-exhaustion are surfaced, never silent (ADR-0006).

Pre-Cornell-authorization, eBird is internal-prototype only and must not enter a paid
path (ADR-0005); the degraded baseline is iNaturalist public records + taxonomy + cache.
"""
