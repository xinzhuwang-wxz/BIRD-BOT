"""Unit tests for (tenant, skill, model) quota/rate limiting (pure, injected clock).

Fair-share: one tenant maxing out its own key must not starve another (ADR-0004)."""
from __future__ import annotations

from birdbot.observability.quota import QuotaKey, QuotaLimiter


def test_per_key_rpm_limit():
    q = QuotaLimiter(rpm=2)
    k = QuotaKey("A", "story", "opus")
    assert q.try_acquire(k)
    assert q.try_acquire(k)
    assert not q.try_acquire(k)  # 3rd within the window denied


def test_one_tenant_maxed_does_not_starve_another():
    q = QuotaLimiter(rpm=1)
    a = QuotaKey("A", "story", "opus")
    b = QuotaKey("B", "story", "opus")
    assert q.try_acquire(a)
    assert not q.try_acquire(a)  # A's key is maxed
    assert q.try_acquire(b)  # B's independent key is unaffected (fair-share)


def test_window_resets_over_time():
    clock = [0.0]
    q = QuotaLimiter(rpm=1, now=lambda: clock[0])
    k = QuotaKey("A", "s", "m")
    assert q.try_acquire(k)
    assert not q.try_acquire(k)
    clock[0] = 61.0
    assert q.try_acquire(k)  # new minute window


def test_concurrency_limit_and_release():
    q = QuotaLimiter(rpm=100, max_concurrent=1)
    k = QuotaKey("A", "s", "m")
    assert q.try_acquire(k)
    assert not q.try_acquire(k)  # concurrent slot taken
    q.release(k)
    assert q.try_acquire(k)  # released
