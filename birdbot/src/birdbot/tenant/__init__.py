"""Multi-tenant context layer (DB-facing part).

The kernel has zero multi-tenant primitives (ADR-0004); isolation is carried entirely
here. This package models the immutable tenant envelope and threads it into the
Postgres row-level-security boundary via ``app.current_tenant``.
"""
