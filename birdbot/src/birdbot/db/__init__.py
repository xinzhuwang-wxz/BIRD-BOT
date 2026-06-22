"""BirdBot persistence layer — asyncpg + raw SQL migrations (ADR-0009).

Business state lives in Postgres (ADR-0002), never in the kernel's session memory.
All business tables carry ``tenant_id`` and are guarded by row-level security; the
runtime connects with a non-owner role so isolation holds even when a query forgets
its ``WHERE tenant_id`` clause (ADR-0004).
"""
