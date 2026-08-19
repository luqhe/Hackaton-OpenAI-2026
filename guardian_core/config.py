from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]


class Environment(StrEnum):
    DEVELOPMENT = "development"
    TEST = "test"
    STAGING = "staging"
    PRODUCTION = "production"


class LogLevel(StrEnum):
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"


TRUE_VALUES = {"1", "true", "yes", "on"}
FALSE_VALUES = {"0", "false", "no", "off"}


def parse_bool(value: str, name: str) -> bool:
    normalized = value.strip().lower()
    if normalized in TRUE_VALUES:
        return True
    if normalized in FALSE_VALUES:
        return False
    raise ValueError(f"{name} must be one of: {', '.join(sorted(TRUE_VALUES | FALSE_VALUES))}")


@dataclass(frozen=True, slots=True)
class GuardianSettings:
    environment: Environment
    database_path: Path
    evidence_directory: Path
    api_url: str
    log_level: LogLevel
    automatic_blocking_enabled: bool
    real_enforcement_enabled: bool
    release_gate_approved: bool

    @classmethod
    def from_env(cls, environ: Mapping[str, str] | None = None) -> GuardianSettings:
        values = os.environ if environ is None else environ
        environment = Environment(values.get("GUARDIAN_ENVIRONMENT", Environment.DEVELOPMENT))
        settings = cls(
            environment=environment,
            database_path=Path(values.get("GUARDIAN_DB_PATH", PROJECT_ROOT / ".data" / "guardian.db")),
            evidence_directory=Path(values.get("GUARDIAN_EVIDENCE_DIR", PROJECT_ROOT / ".data" / "evidence")),
            api_url=values.get("GUARDIAN_API_URL", "http://127.0.0.1:8000").rstrip("/"),
            log_level=LogLevel(values.get("GUARDIAN_LOG_LEVEL", LogLevel.INFO).upper()),
            automatic_blocking_enabled=parse_bool(
                values.get("GUARDIAN_AUTOMATIC_BLOCKING_ENABLED", "true"),
                "GUARDIAN_AUTOMATIC_BLOCKING_ENABLED",
            ),
            real_enforcement_enabled=parse_bool(
                values.get("GUARDIAN_REAL_ENFORCEMENT_ENABLED", "false"),
                "GUARDIAN_REAL_ENFORCEMENT_ENABLED",
            ),
            release_gate_approved=parse_bool(
                values.get("GUARDIAN_RELEASE_GATE_APPROVED", "false"),
                "GUARDIAN_RELEASE_GATE_APPROVED",
            ),
        )
        settings.validate()
        return settings

    def validate(self) -> None:
        if not self.api_url.startswith(("http://", "https://")):
            raise ValueError("GUARDIAN_API_URL must start with http:// or https://")
        if self.environment in {Environment.STAGING, Environment.PRODUCTION}:
            if self.automatic_blocking_enabled and not self.release_gate_approved:
                raise ValueError(
                    "Automatic blocking in staging/production requires an approved release gate "
                    "(GUARDIAN_RELEASE_GATE_APPROVED=true)"
                )
            if self.real_enforcement_enabled and not self.release_gate_approved:
                raise ValueError(
                    "Real enforcement in staging/production requires an approved release gate "
                    "(GUARDIAN_RELEASE_GATE_APPROVED=true)"
                )
