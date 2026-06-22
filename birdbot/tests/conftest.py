"""Fixtures for Postgres RLS integration tests (ADR-0009).

These tests need a real, throwaway Postgres. Point BIRDBOT_TEST_DATABASE_URL at one
(admin/superuser DSN); without it the integration tests skip. The fixtures play the
deploy environment: they ensure the non-owner ``birdbot_app`` role exists, then run
migrations with the admin connection. Business work goes through the app role so RLS
is actually enforced.
"""
from __future__ import annotations

import os
from urllib.parse import urlsplit, urlunsplit

import asyncpg
import pytest
import pytest_asyncio

from birdbot.db.migrations import apply_migrations
from birdbot.db.pool import Database

_ADMIN_DSN = os.environ.get("BIRDBOT_TEST_DATABASE_URL")
_APP_ROLE = "birdbot_app"
_APP_PW = "birdbot_test_pw"  # test-only; real creds come from the deploy environment

_SKIP_REASON = (
    "BIRDBOT_TEST_DATABASE_URL not set. Start a throwaway Postgres, e.g.:\n"
    "  docker run -d --name birdbot-test-pg -e POSTGRES_PASSWORD=postgres "
    "-e POSTGRES_DB=birdbot_test -p 5433:5432 postgres:16-alpine\n"
    "  export BIRDBOT_TEST_DATABASE_URL="
    "postgresql://postgres:postgres@localhost:5433/birdbot_test"
)


def _app_dsn() -> str:
    """The admin DSN with creds swapped to the non-owner application role."""
    parts = urlsplit(_ADMIN_DSN)
    netloc = f"{_APP_ROLE}:{_APP_PW}@{parts.hostname}"
    if parts.port:
        netloc += f":{parts.port}"
    return urlunsplit((parts.scheme, netloc, parts.path, parts.query, parts.fragment))


async def _provision() -> None:
    """Ensure the non-owner role exists, then migrate — with the admin connection."""
    admin = await asyncpg.connect(_ADMIN_DSN)
    try:
        await admin.execute(
            f"DO $$ BEGIN "
            f"IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{_APP_ROLE}') THEN "
            f"CREATE ROLE {_APP_ROLE} LOGIN PASSWORD '{_APP_PW}'; "
            f"END IF; END $$;"
        )
        await apply_migrations(admin)
    finally:
        await admin.close()


@pytest_asyncio.fixture
async def admin_conn():
    """An admin (owner) connection with the schema already provisioned."""
    if not _ADMIN_DSN:
        pytest.skip(_SKIP_REASON)
    await _provision()
    conn = await asyncpg.connect(_ADMIN_DSN)
    try:
        yield conn
    finally:
        await conn.close()


@pytest_asyncio.fixture
async def app_db():
    """A Database on the non-owner role against a freshly-truncated events table."""
    if not _ADMIN_DSN:
        pytest.skip(_SKIP_REASON)
    await _provision()
    admin = await asyncpg.connect(_ADMIN_DSN)
    try:
        await admin.execute("TRUNCATE events")  # TRUNCATE is owner-level, bypasses RLS
    finally:
        await admin.close()
    db = await Database.connect(_app_dsn())
    try:
        yield db
    finally:
        await db.close()


@pytest_asyncio.fixture
async def unscoped_app_conn():
    """A raw non-owner connection that never sets app.current_tenant (fail-closed tests)."""
    if not _ADMIN_DSN:
        pytest.skip(_SKIP_REASON)
    await _provision()
    conn = await asyncpg.connect(_app_dsn())
    try:
        yield conn
    finally:
        await conn.close()
