"""Minimal forward-only migration runner (ADR-0009).

No ORM, no Alembic: numbered ``migrations/*.sql`` files are applied in order, each
recorded in ``schema_migrations`` so re-running is idempotent. Run with an admin/owner
connection — DDL and GRANTs are owner operations; the business runtime connects with a
non-owner role instead.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

_MIGRATIONS_DIR = Path(__file__).parent / "migrations"


async def apply_migrations(conn: Any, migrations_dir: Path | None = None) -> list[str]:
    """Apply any unapplied ``*.sql`` migrations in lexical order; return those applied now.

    Idempotent: already-recorded versions are skipped, so a second call returns ``[]``.
    Each migration runs in its own transaction together with its bookkeeping insert, so
    a failed migration leaves no partial version record.
    """
    migrations_dir = migrations_dir or _MIGRATIONS_DIR
    await conn.execute(
        """
        CREATE TABLE IF NOT EXISTS schema_migrations (
            version    text PRIMARY KEY,
            applied_at timestamptz NOT NULL DEFAULT now()
        )
        """
    )
    applied = {
        row["version"] for row in await conn.fetch("SELECT version FROM schema_migrations")
    }
    applied_now: list[str] = []
    for path in sorted(migrations_dir.glob("*.sql")):
        version = path.stem
        if version in applied:
            continue
        sql = path.read_text(encoding="utf-8")
        async with conn.transaction():
            await conn.execute(sql)
            await conn.execute(
                "INSERT INTO schema_migrations (version) VALUES ($1)", version
            )
        applied_now.append(version)
    return applied_now
