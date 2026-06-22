"""HTTP ingress for BirdEvents (ADR-0003 fast-stage sync entry, ADR-0010 FastAPI).

IoT platforms POST a versioned BirdEvent here; the ingress validates it, lands it in
Postgres under a tenant-derived idempotency key, and returns a 202 acceptance receipt
with a status_url. Tenant identity rides in the BirdEvent body for v0 (auth pipeline is
a later slice) and is carried as a TenantEnvelope through deterministic components.
"""
