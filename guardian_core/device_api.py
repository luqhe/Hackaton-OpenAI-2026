from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

from guardian_core.models import PolicyDecision, RiskAssessment


class PairingChallengeCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    child_id: str = Field(min_length=1, max_length=100)


class PairingChallengeIssued(BaseModel):
    challenge_id: str
    code: str
    expires_at: datetime


class PairingConfirmation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    challenge_id: str = Field(min_length=20, max_length=100)
    code: str = Field(
        pattern=r"(?i)^[23456789ABCDEFGHJKLMNPQRSTUVWXYZ]{4}-?[23456789ABCDEFGHJKLMNPQRSTUVWXYZ]{4}$"
    )
    device_name: str = Field(min_length=1, max_length=120)
    platform: str = Field(min_length=1, max_length=40)
    installation_id: str = Field(pattern=r"^install-[A-Za-z0-9_-]{12,80}$")
    public_key: str = Field(pattern=r"^[A-Za-z0-9_-]{43}$")


class DeviceCredentialIssued(BaseModel):
    credential_id: str
    device_id: str
    expires_at: datetime
    protocol_version: str


class AgentIncidentCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    application: str = Field(min_length=1, max_length=120)
    occurred_at: datetime
    assessment: RiskAssessment
    decision: PolicyDecision
    deduplication_key: str = Field(min_length=8, max_length=128)


class AgentTelemetryUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    observed_at: datetime
    screen_changes: Annotated[int, Field(ge=0, le=1_000_000)] = 0
    media_sessions: Annotated[int, Field(ge=0, le=1_000_000)] = 0
    suspicious_events: Annotated[int, Field(ge=0, le=1_000_000)] = 0
    app_name: str | None = Field(default=None, max_length=120)
    session_seconds: Annotated[int, Field(ge=0, le=86_400)] = 0


class CommandExecutionResult(StrEnum):
    EXECUTED = "EXECUTED"
    FAILED = "FAILED"


class CommandAcknowledgement(BaseModel):
    model_config = ConfigDict(extra="forbid")

    result: CommandExecutionResult
    error_code: str | None = Field(default=None, pattern=r"^[A-Z0-9_]{2,64}$")


class CredentialRotationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    public_key: str = Field(pattern=r"^[A-Za-z0-9_-]{43}$")
    idempotency_key: str = Field(pattern=r"^[A-Za-z0-9_-]{16,100}$")
