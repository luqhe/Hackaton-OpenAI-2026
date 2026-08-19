from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass, field
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
    object_store_provider: str
    object_store_bucket: str
    object_store_endpoint: str
    kms_key_id: str
    audit_hmac_key_id: str
    audit_hmac_secret: bytes = field(repr=False)
    rate_limit_hmac_secret: bytes = field(repr=False)
    evidence_grant_ttl_seconds: int

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
        settings = cls(
            environment=environment,
            database=database,
            object_store_provider=values.get("GUARDIAN_OBJECT_STORE_PROVIDER", "filesystem").lower(),
            object_store_bucket=values.get("GUARDIAN_OBJECT_STORE_BUCKET", ""),
            object_store_endpoint=values.get("GUARDIAN_OBJECT_STORE_ENDPOINT", ""),
            kms_key_id=values.get("GUARDIAN_KMS_KEY_ID", ""),
            audit_hmac_key_id=values.get("GUARDIAN_AUDIT_HMAC_KEY_ID", "development-audit-v1"),
            audit_hmac_secret=values.get(
                "GUARDIAN_AUDIT_HMAC_SECRET", "development-audit-secret-key-32"
            ).encode(),
            rate_limit_hmac_secret=values.get(
                "GUARDIAN_RATE_LIMIT_HMAC_SECRET", "development-rate-secret-key-000"
            ).encode(),
            evidence_grant_ttl_seconds=_parse_pool_size(values, "GUARDIAN_EVIDENCE_GRANT_TTL_SECONDS", 120),
        )
        settings.validate()
        return settings

    def validate(self) -> None:
        if self.object_store_provider not in {"filesystem", "s3"}:
            raise ValueError("GUARDIAN_OBJECT_STORE_PROVIDER must be filesystem or s3")
        if not 30 <= self.evidence_grant_ttl_seconds <= 300:
            raise ValueError("Evidence grant TTL must be between 30 and 300 seconds")
        if self.environment in MANAGED_ENVIRONMENTS:
            managed_values = (
                self.database.url,
                self.object_store_bucket,
                self.object_store_endpoint,
                self.kms_key_id,
                self.audit_hmac_key_id,
                self.audit_hmac_secret.decode(errors="ignore"),
                self.rate_limit_hmac_secret.decode(errors="ignore"),
            )
            if any("CHANGE_ME" in value or "REPLACE_WITH" in value for value in managed_values):
                raise ValueError("Managed data-security configuration contains a placeholder")
            if self.object_store_provider != "s3":
                raise ValueError("Managed environments require private S3-compatible object storage")
            if not self.object_store_bucket or not self.kms_key_id:
                raise ValueError("Managed object storage requires a private bucket and KMS key")
            parsed_endpoint = urlparse(self.object_store_endpoint)
            if parsed_endpoint.scheme != "https" or not parsed_endpoint.hostname:
                raise ValueError("Managed object storage endpoint must use HTTPS")
            if not self.audit_hmac_key_id or len(self.audit_hmac_secret) < 32:
                raise ValueError("Managed audit HMAC key_id and 32-byte secret are required")
            if len(self.rate_limit_hmac_secret) < 32:
                raise ValueError("Managed rate-limit HMAC secret must contain at least 32 bytes")


def _parse_pool_size(values: Mapping[str, str], name: str, default: int) -> int:
    raw = values.get(name)
    if raw is None:
        return default
    try:
        return int(raw)
    except ValueError as error:
        raise ValueError(f"{name} must be an integer") from error
