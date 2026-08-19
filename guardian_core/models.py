from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, model_validator


def utc_now() -> datetime:
    return datetime.now(UTC)


class RiskLevel(StrEnum):
    SAFE = "SAFE"
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


class RiskCategory(StrEnum):
    ADULT_CONTENT = "ADULT_CONTENT"
    HATE_SPEECH = "HATE_SPEECH"
    DANGEROUS_CONTACT = "DANGEROUS_CONTACT"
    OTHER = "OTHER"


class RiskDirection(StrEnum):
    CONTENT_CONSUMPTION = "CONTENT_CONSUMPTION"
    CHILD_AS_TARGET = "CHILD_AS_TARGET"
    CHILD_AS_ACTOR = "CHILD_AS_ACTOR"


class PolicyAction(StrEnum):
    ALLOW = "ALLOW"
    ALERT = "ALERT"
    BLOCK = "BLOCK"


class EnforcementAction(StrEnum):
    IGNORE = "IGNORE"
    LOG = "LOG"
    ALERT = "ALERT"
    BLOCK = "BLOCK"


class IncidentStatus(StrEnum):
    DETECTED = "DETECTED"
    BLOCKED = "BLOCKED"
    UNLOCK_REQUESTED = "UNLOCK_REQUESTED"
    UNLOCKED = "UNLOCKED"
    KEPT_BLOCKED = "KEPT_BLOCKED"


class CommandType(StrEnum):
    UNLOCK_APPLICATION = "UNLOCK_APPLICATION"


class CommandStatus(StrEnum):
    PENDING = "PENDING"
    ACKNOWLEDGED = "ACKNOWLEDGED"


class PilotOnboardingStage(StrEnum):
    STARTED = "STARTED"
    PRIVACY_REVIEWED = "PRIVACY_REVIEWED"
    CONSENT_RECORDED = "CONSENT_RECORDED"
    CHILD_PROFILE_CONFIGURED = "CHILD_PROFILE_CONFIGURED"
    DEVICE_PAIRED = "DEVICE_PAIRED"
    PERMISSIONS_GRANTED = "PERMISSIONS_GRANTED"
    FIRST_HEALTHY_HEARTBEAT = "FIRST_HEALTHY_HEARTBEAT"
    SHADOW_READY = "SHADOW_READY"


class ConversationMessage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    timestamp: datetime = Field(default_factory=utc_now)
    speaker: str = Field(min_length=1, max_length=80)
    text: str = Field(min_length=1, max_length=4000)


class Observation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    timestamp: datetime = Field(default_factory=utc_now)
    app_name: str = Field(min_length=1, max_length=120)
    window_title: str = Field(default="", max_length=500)
    screen_hash: str | None = Field(default=None, max_length=128)
    media_detected: bool = False
    visible_text: str = Field(default="", max_length=20_000)
    recent_messages: list[ConversationMessage] = Field(default_factory=list, max_length=10)


class RiskAssessment(BaseModel):
    """Classifier output. It intentionally contains no enforcement action."""

    model_config = ConfigDict(extra="forbid")

    risk: RiskLevel
    category: RiskCategory | None = None
    direction: RiskDirection | None = None
    confidence: Annotated[float, Field(ge=0, le=1)]
    evidence: list[str] = Field(default_factory=list, max_length=12)
    explanation: str = Field(min_length=1, max_length=4000)

    @model_validator(mode="after")
    def validate_safe_semantics(self) -> RiskAssessment:
        if self.risk == RiskLevel.SAFE and (self.category is not None or self.direction is not None):
            raise ValueError("SAFE assessments cannot have category or direction")
        if self.risk != RiskLevel.SAFE and (self.category is None or self.direction is None):
            raise ValueError("Non-SAFE assessments require category and direction")
        return self


class PolicyRule(BaseModel):
    model_config = ConfigDict(extra="forbid")

    category: RiskCategory
    action: PolicyAction
    minimum_risk: RiskLevel = RiskLevel.HIGH
    minimum_confidence: Annotated[float, Field(ge=0, le=1)] = 0.75


class PolicyDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action: EnforcementAction
    matched_rule: PolicyRule | None = None
    reason: str


class IncidentCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    child_id: str = Field(min_length=1, max_length=100)
    device_id: str = Field(min_length=1, max_length=100)
    application: str = Field(min_length=1, max_length=120)
    occurred_at: datetime = Field(default_factory=utc_now)
    assessment: RiskAssessment
    decision: PolicyDecision
    deduplication_key: str = Field(min_length=8, max_length=128)


class Incident(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    child_id: str
    device_id: str
    application: str
    occurred_at: datetime
    category: RiskCategory
    direction: RiskDirection
    severity: RiskLevel
    confidence: float
    explanation: str
    evidence: list[str]
    policy_action: EnforcementAction
    status: IncidentStatus
    child_explanation: str | None = None
    screenshot_urls: list[str] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime


class UnlockRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    explanation: str = Field(min_length=3, max_length=1000)


class DevicePairRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    child_id: str = Field(min_length=1, max_length=100)
    device_name: str = Field(min_length=1, max_length=120)
    platform: str = Field(default="macOS", max_length=40)


class Device(BaseModel):
    id: str
    child_id: str
    name: str
    platform: str
    paired_at: datetime
    last_seen_at: datetime | None = None
    protection_status: str


class DeviceHeartbeat(BaseModel):
    model_config = ConfigDict(extra="forbid")

    agent_version: str = Field(min_length=1, max_length=40)
    screen_recording_permission: bool
    accessibility_permission: bool
    observer_healthy: bool
    offline_queue_depth: Annotated[int, Field(ge=0, le=1000)] = 0
    observed_at: datetime = Field(default_factory=utc_now)


class PilotOnboardingEventCreate(BaseModel):
    """Allowlisted funnel event. It intentionally has no arbitrary metadata/content field."""

    model_config = ConfigDict(extra="forbid")

    child_id: str = Field(min_length=1, max_length=100)
    device_id: str | None = Field(default=None, min_length=1, max_length=100)
    session_id: str = Field(min_length=8, max_length=128)
    stage: PilotOnboardingStage
    occurred_at: datetime = Field(default_factory=utc_now)
    idempotency_key: str = Field(min_length=8, max_length=128)


class PilotOnboardingEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    child_id: str
    device_id: str | None
    session_id: str
    stage: PilotOnboardingStage
    occurred_at: datetime
    created_at: datetime


class PilotFunnelStageMetric(BaseModel):
    model_config = ConfigDict(extra="forbid")

    stage: PilotOnboardingStage
    event_count: int
    unique_sessions: int


class PilotMetricsReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    window_started_at: datetime
    generated_at: datetime
    onboarding: list[PilotFunnelStageMetric]
    health_sample_count: int
    healthy_health_sample_count: int
    agent_health_percent: float | None
    heartbeat_age_max_seconds: float | None
    offline_queue_depth_max: int | None
    command_ack_count: int
    command_ack_latency_p50_ms: float | None
    command_ack_latency_p95_ms: float | None
    command_ack_latency_max_ms: float | None


class DeviceCommand(BaseModel):
    id: int
    device_id: str
    incident_id: str
    type: CommandType
    application: str
    status: CommandStatus
    created_at: datetime
    acknowledged_at: datetime | None = None


class TelemetryUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    child_id: str
    observed_at: datetime = Field(default_factory=utc_now)
    screen_changes: Annotated[int, Field(ge=0, le=1_000_000)] = 0
    media_sessions: Annotated[int, Field(ge=0, le=1_000_000)] = 0
    suspicious_events: Annotated[int, Field(ge=0, le=1_000_000)] = 0
    app_name: str | None = Field(default=None, max_length=120)
    session_seconds: Annotated[int, Field(ge=0, le=86_400)] = 0


class DailyAppUsage(BaseModel):
    app: str
    seconds: int


class DailyReport(BaseModel):
    child_id: str
    child_name: str
    date: str
    total_seconds: int
    apps: list[DailyAppUsage]
    incident_count: int
    screen_changes: int
    media_sessions: int
    suspicious_events: int
    interventions: int
    evidence_count: int


class ProductCapabilities(BaseModel):
    model_config = ConfigDict(extra="forbid")

    environment: str
    api_version: str
    fixture_analysis: bool
    real_screen_observation: bool
    local_ocr: bool
    system_audio: bool
    microphone: bool
    camera: bool
    simulated_enforcement: bool
    real_macos_enforcement: bool
    automatic_blocking_scope: str
    authentication: bool
    tenant_isolation: bool
    production_ready: bool
    notes: list[str]
