"""Workflow Runtime v0 — DBOS-style durable execution on Postgres (ADR-0002).

Business workflow reliability (state, idempotency, timeout, bounded retry,
transactional outbox) lives in Postgres, not in the kernel's Cron/Goal or session
memory. A step is journaled before it runs and replayed (not re-executed) on restart;
results leave via a transactional outbox delivered at-least-once.
"""
