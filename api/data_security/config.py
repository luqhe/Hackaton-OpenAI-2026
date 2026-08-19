from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass
from urllib.parse import parse_qs, urlparse

from guardian_core.config import PROJECT_ROOT, Environment

POSTGRES_SCHEMES = {"postgres", "postgresql", "postgresql+psycopg"}
LOCAL_ENVIRONMENTS = {Environment.DEVELOPMENT, Environment.TEST}
MANAGED_ENVIRONMENTS = {Environment.STAGING, Environment.PRODUCTION}


@dataclass(frozen=True, slots=True)
class DatabaseConfig:
    environment: Environment
    url: str
    pool_min_size: int = 1
    pool_max_size: int = 8

    @property
    def scheme(self) -> str:
        return urlparse(self.url).scheme.lower()

    def validate(self) -> None:
        if self.pool_min_size < 1 or self.pool_max_size < self.pool_min_size:
            raise ValueError("Database pool sizes must satisfy 1 <= min <= max")
        if self.pool_max_size > 64:
            raise ValueError("Database pool maximum cannot exceed 64 connections")

        parsed = urlparse(self.url)
        if parsed.scheme == "sqlite":
            if self.environment not in LOCAL_ENVIRONMENTS:
                raise ValueError("Staging and production require managed PostgreSQL")
            if not parsed.path:
                raise ValueError("SQLite database URL must include a path")
            return

        if parsed.scheme not in POSTGRES_SCHEMES:
            raise ValueError("Database URL must use SQLite locally or PostgreSQL")
        if not parsed.hostname or not parsed.path.strip("/"):
            raise ValueError("PostgreSQL URL must include a host and database name")
        if self.environment in MANAGED_ENVIRONMENTS:
            ssl_mode = parse_qs(parsed.query).get("sslmode", [""])[-1]
            if ssl_mode != "verify-full":
                raise ValueError("Managed PostgreSQL requires sslmode=verify-full")


@dataclass(frozen=True, slots=True)
class DataSecuritySettings:
    environment: Environment
    database: DatabaseConfig

    @classmethod
    def from_env(cls, environ: Mapping[str, str] | None = None) -> DataSecuritySettings:
        values = os.environ if environ is None else environ
        environment = Environment(values.get("GUARDIAN_ENVIRONMENT", Environment.DEVELOPMENT))
        default_url = f"sqlite:///{PROJECT_ROOT / '.data' / 'guardian.db'}"
        database = DatabaseConfig(
            environment=environment,
            url=values.get("GUARDIAN_DATABASE_URL", default_url),
            pool_min_size=_parse_pool_size(values, "GUARDIAN_DATABASE_POOL_MIN", 1),
            pool_max_size=_parse_pool_size(values, "GUARDIAN_DATABASE_POOL_MAX", 8),
        )
        database.validate()
        return cls(environment=environment, database=database)


def _parse_pool_size(values: Mapping[str, str], name: str, default: int) -> int:
    raw = values.get(name)
    if raw is None:
        return default
    try:
        return int(raw)
    except ValueError as error:
        raise ValueError(f"{name} must be an integer") from error
