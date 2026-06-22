"""asyncpg connection pool with per-request tenant scoping (ADR-0004 / ADR-0009).

The business runtime connects through this pool with a non-owner role, so Postgres
row-level security is enforced. ``tenant_scope`` sets ``app.current_tenant`` as a
transaction-local GUC via parameterized ``set_config`` — the tenant id never touches
SQL text, and the setting resets on commit/rollback so it cannot leak to the next
request that reuses a pooled connection.
"""
from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

import asyncpg


class Database:
    """Thin owner of an asyncpg pool that hands out tenant-scoped connections."""

    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    @classmethod
    async def connect(cls, dsn: str, **pool_kwargs: Any) -> Database:
        pool = await asyncpg.create_pool(dsn, **pool_kwargs)
        return cls(pool)

    async def close(self) -> None:
        await self._pool.close()

    @asynccontextmanager
    async def tenant_scope(self, tenant_id: str) -> AsyncIterator[asyncpg.Connection]:
        """Yield a connection scoped to ``tenant_id`` for the life of one transaction.

        All work inside the block runs under ``app.current_tenant = tenant_id``, so RLS
        filters every query to this tenant — even one that forgets ``WHERE tenant_id``.
        """
        if not tenant_id:
            raise ValueError("tenant_id is required for tenant_scope")
        async with self._pool.acquire() as conn:
            async with conn.transaction():
                # set_config(..., is_local=true) == SET LOCAL; parameterized (no injection).
                await conn.execute(
                    "SELECT set_config('app.current_tenant', $1, true)", tenant_id
                )
                yield conn
