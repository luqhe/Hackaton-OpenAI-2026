from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta

from api.data_security.rate_limit import (
    DEFAULT_RATE_LIMITS,
    InMemoryRateLimitBackend,
    RateLimiter,
    RateLimitPolicy,
    RouteClass,
)

NOW = datetime(2026, 8, 19, 12, tzinfo=UTC)


def _limiter(limit: int = 1):
    backend = InMemoryRateLimitBackend()
    policies = {
        route_class: RateLimitPolicy(limit=limit, window=timedelta(minutes=1)) for route_class in RouteClass
    }
    limiter = RateLimiter(backend, policies=policies, identity_hmac_key=b"r" * 32)
    return limiter, backend


def test_evidence_abuse_cannot_starve_unlock_ack_or_heartbeat() -> None:
    limiter, _ = _limiter()
    assert limiter.check("principal-1", RouteClass.EVIDENCE_READ, now=NOW).allowed
    assert not limiter.check("principal-1", RouteClass.EVIDENCE_READ, now=NOW).allowed

    assert limiter.check("principal-1", RouteClass.UNLOCK, now=NOW).allowed
    assert limiter.check("principal-1", RouteClass.COMMAND_ACK, now=NOW).allowed
    assert limiter.check("principal-1", RouteClass.HEARTBEAT, now=NOW).allowed


def test_limiter_hashes_identity_and_returns_bounded_retry_after() -> None:
    limiter, backend = _limiter()
    limiter.check("parent@example.test", RouteClass.LOGIN, now=NOW)

    decision = limiter.check("parent@example.test", RouteClass.LOGIN, now=NOW)

    assert decision.allowed is False
    assert decision.retry_after_seconds == 60
    assert "parent@example.test" not in repr(backend.windows)
    assert len(decision.bucket_fingerprint) == 12


def test_window_reset_does_not_reuse_expired_count() -> None:
    limiter, _ = _limiter()
    limiter.check("principal-1", RouteClass.PAIRING, now=NOW)
    assert not limiter.check("principal-1", RouteClass.PAIRING, now=NOW).allowed

    reset = limiter.check(
        "principal-1",
        RouteClass.PAIRING,
        now=NOW + timedelta(seconds=60),
    )

    assert reset.allowed is True
    assert reset.remaining == 0


def test_in_memory_backend_consumes_atomically_under_concurrency() -> None:
    limiter, _ = _limiter(limit=10)

    with ThreadPoolExecutor(max_workers=16) as executor:
        decisions = list(
            executor.map(
                lambda _: limiter.check("principal-1", RouteClass.GENERAL, now=NOW),
                range(50),
            )
        )

    assert sum(decision.allowed for decision in decisions) == 10


def test_default_policy_has_independent_critical_route_classes() -> None:
    assert set(DEFAULT_RATE_LIMITS) == set(RouteClass)
    critical = {
        RouteClass.UNLOCK,
        RouteClass.COMMAND_ACK,
        RouteClass.HEARTBEAT,
    }

    assert critical.isdisjoint(
        {
            RouteClass.LOGIN,
            RouteClass.PAIRING,
            RouteClass.EVIDENCE_READ,
            RouteClass.EVIDENCE_WRITE,
            RouteClass.GENERAL,
        }
    )
