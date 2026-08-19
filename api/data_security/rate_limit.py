from __future__ import annotations

import hashlib
import hmac
import math
import threading
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import Any, Protocol


class RouteClass(StrEnum):
    LOGIN = "LOGIN"
    PAIRING = "PAIRING"
    EVIDENCE_READ = "EVIDENCE_READ"
    EVIDENCE_WRITE = "EVIDENCE_WRITE"
    GENERAL = "GENERAL"
    UNLOCK = "UNLOCK"
    COMMAND_ACK = "COMMAND_ACK"
    HEARTBEAT = "HEARTBEAT"


@dataclass(frozen=True, slots=True)
class RateLimitPolicy:
    limit: int
    window: timedelta

    def __post_init__(self) -> None:
        if self.limit < 1:
            raise ValueError("Rate limit must be positive")
        if self.window < timedelta(seconds=1) or self.window > timedelta(hours=24):
            raise ValueError("Rate-limit window must be between 1 second and 24 hours")


DEFAULT_RATE_LIMITS: Mapping[RouteClass, RateLimitPolicy] = {
    RouteClass.LOGIN: RateLimitPolicy(5, timedelta(minutes=1)),
    RouteClass.PAIRING: RateLimitPolicy(10, timedelta(minutes=1)),
    RouteClass.EVIDENCE_READ: RateLimitPolicy(30, timedelta(minutes=1)),
    RouteClass.EVIDENCE_WRITE: RateLimitPolicy(10, timedelta(minutes=1)),
    RouteClass.GENERAL: RateLimitPolicy(120, timedelta(minutes=1)),
    RouteClass.UNLOCK: RateLimitPolicy(120, timedelta(minutes=1)),
    RouteClass.COMMAND_ACK: RateLimitPolicy(240, timedelta(minutes=1)),
    RouteClass.HEARTBEAT: RateLimitPolicy(120, timedelta(minutes=1)),
}


@dataclass(frozen=True, slots=True)
class BackendConsumption:
    accepted: bool
    count: int


@dataclass(frozen=True, slots=True)
class RateLimitDecision:
    allowed: bool
    remaining: int
    retry_after_seconds: int
    bucket_fingerprint: str


class RateLimitBackend(Protocol):
    def consume(
        self,
        *,
        bucket_key: str,
        route_class: RouteClass,
        window_started_at: datetime,
        expires_at: datetime,
        limit: int,
        now: datetime,
    ) -> BackendConsumption: ...


class InMemoryRateLimitBackend:
    def __init__(self) -> None:
        self.windows: dict[tuple[str, RouteClass, datetime], tuple[int, datetime]] = {}
        self._lock = threading.Lock()

    def consume(
        self,
        *,
        bucket_key: str,
        route_class: RouteClass,
        window_started_at: datetime,
        expires_at: datetime,
        limit: int,
        now: datetime,
    ) -> BackendConsumption:
        key = (bucket_key, route_class, window_started_at)
        with self._lock:
            for stale_key, (_, stale_expiry) in tuple(self.windows.items()):
                if stale_key[:2] == key[:2] and stale_expiry <= now:
                    self.windows.pop(stale_key, None)
            count, _ = self.windows.get(key, (0, expires_at))
            if count >= limit:
                return BackendConsumption(False, count)
            count += 1
            self.windows[key] = (count, expires_at)
            return BackendConsumption(True, count)


POSTGRES_RATE_LIMIT_CONSUME_SQL = """
INSERT INTO rate_limit_windows(
    bucket_key, route_class, window_started_at, request_count, expires_at
) VALUES (%s, %s, %s, 1, %s)
ON CONFLICT(bucket_key, route_class, window_started_at) DO UPDATE SET
    request_count = rate_limit_windows.request_count + 1,
    expires_at = EXCLUDED.expires_at
WHERE rate_limit_windows.request_count < %s
RETURNING request_count
"""


class PostgresRateLimitBackend:
    """Atomic multi-process backend using the data-security PostgreSQL table."""

    def __init__(self, transaction_factory: Callable[[], Any]):
        self.transaction_factory = transaction_factory

    def consume(
        self,
        *,
        bucket_key: str,
        route_class: RouteClass,
        window_started_at: datetime,
        expires_at: datetime,
        limit: int,
        now: datetime,
    ) -> BackendConsumption:
        del now
        with self.transaction_factory() as connection:
            row = connection.execute(
                POSTGRES_RATE_LIMIT_CONSUME_SQL,
                (bucket_key, route_class, window_started_at, expires_at, limit),
            ).fetchone()
            if row is None:
                current = connection.execute(
                    """
                    SELECT request_count FROM rate_limit_windows
                    WHERE bucket_key = %s AND route_class = %s AND window_started_at = %s
                    """,
                    (bucket_key, route_class, window_started_at),
                ).fetchone()
                return BackendConsumption(False, int(current[0]) if current else limit)
            return BackendConsumption(True, int(row[0]))


class RateLimiter:
    def __init__(
        self,
        backend: RateLimitBackend,
        *,
        policies: Mapping[RouteClass, RateLimitPolicy] = DEFAULT_RATE_LIMITS,
        identity_hmac_key: bytes,
    ):
        missing = set(RouteClass) - set(policies)
        if missing:
            raise ValueError(f"Rate-limit policies missing route classes: {sorted(missing)}")
        if len(identity_hmac_key) < 32:
            raise ValueError("Rate-limit identity HMAC key must contain at least 32 bytes")
        self.backend = backend
        self.policies = dict(policies)
        self.identity_hmac_key = identity_hmac_key

    def check(
        self,
        principal: str,
        route_class: RouteClass,
        *,
        now: datetime | None = None,
    ) -> RateLimitDecision:
        if not principal or len(principal) > 512:
            raise ValueError("Rate-limit principal must be a bounded identifier")
        checked_at = now or datetime.now(UTC)
        if checked_at.tzinfo is None:
            raise ValueError("Rate-limit clock must be timezone-aware")
        policy = self.policies[route_class]
        window_seconds = int(policy.window.total_seconds())
        epoch_seconds = int(checked_at.timestamp())
        window_epoch = epoch_seconds - (epoch_seconds % window_seconds)
        window_started_at = datetime.fromtimestamp(window_epoch, tz=UTC)
        expires_at = window_started_at + policy.window
        bucket_key = hmac.new(
            self.identity_hmac_key,
            principal.encode(),
            hashlib.sha256,
        ).hexdigest()
        consumed = self.backend.consume(
            bucket_key=bucket_key,
            route_class=route_class,
            window_started_at=window_started_at,
            expires_at=expires_at,
            limit=policy.limit,
            now=checked_at,
        )
        retry_after = 0
        if not consumed.accepted:
            retry_after = max(1, math.ceil((expires_at - checked_at).total_seconds()))
        return RateLimitDecision(
            allowed=consumed.accepted,
            remaining=max(0, policy.limit - consumed.count),
            retry_after_seconds=retry_after,
            bucket_fingerprint=bucket_key[:12],
        )
