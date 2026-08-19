"""HTTP composition for the Stage 4 family/reporting services.

The authenticated family is supplied by an injected R2 dependency. No endpoint
accepts a caller-selected family id.
"""

from collections.abc import Callable
from datetime import UTC, date, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, Field

from guardian_core.family_reporting import (
    CaseKind,
    DuplicateConflict,
    EvidenceConsentRequired,
    FamilyReportingService,
    NotificationChannel,
    RetentionKind,
    SafetyMetric,
    ScopeViolation,
    SessionSafetyEvent,
    SessionUpload,
)


def _utc_now() -> datetime:
    return datetime.now(UTC)


class SessionSafetyEventInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    event_id: str = Field(min_length=1, max_length=128)
    occurred_at: datetime
    metric: SafetyMetric
    count: int = Field(default=1, ge=1, le=1_000_000)


class SessionUploadInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    child_id: str = Field(min_length=1, max_length=100)
    device_id: str = Field(min_length=1, max_length=100)
    source_event_id: str = Field(min_length=1, max_length=128)
    source: str = Field(pattern="^OBSERVER_SESSION$")
    started_at: datetime
    ended_at: datetime
    safety_events: list[SessionSafetyEventInput] = Field(default_factory=list, max_length=1000)
    captured_offline: bool = False


class RetentionUpdateInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    retention_days: dict[RetentionKind, int]


class NotificationChannelsInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    channels: frozenset[NotificationChannel]


class SupportCaseInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: CaseKind
    summary: str = Field(min_length=1, max_length=500)
    child_id: str | None = Field(default=None, max_length=100)
    incident_id: str | None = Field(default=None, max_length=100)
    evidence_ids: tuple[str, ...] = Field(default=(), max_length=3)
    evidence_consent: bool = False


def create_stage4_family_router(
    service: FamilyReportingService,
    *,
    current_family_id: Callable[[], str],
    clock: Callable[[], datetime] = _utc_now,
    notification_channels_changed: Callable[[str, frozenset[NotificationChannel]], None] | None = None,
) -> APIRouter:
    """Build routes around R1/R2/R3 adapters and an R2 auth dependency."""

    router = APIRouter(prefix="/api/family", tags=["family-reporting"])

    @router.get("/scope")
    def family_scope(family_id: Annotated[str, Depends(current_family_id)]) -> tuple:
        return service.family_scope(family_id)

    @router.post("/session-events", status_code=status.HTTP_202_ACCEPTED)
    def ingest_session(
        payload: SessionUploadInput,
        family_id: Annotated[str, Depends(current_family_id)],
    ) -> object:
        try:
            upload = SessionUpload(
                child_id=payload.child_id,
                device_id=payload.device_id,
                source_event_id=payload.source_event_id,
                source=payload.source,
                started_at=payload.started_at,
                ended_at=payload.ended_at,
                safety_events=tuple(
                    SessionSafetyEvent(
                        event_id=event.event_id,
                        occurred_at=event.occurred_at,
                        metric=event.metric,
                        count=event.count,
                    )
                    for event in payload.safety_events
                ),
                captured_offline=payload.captured_offline,
            )
            return service.ingest_session(family_id, upload, synced_at=clock())
        except ScopeViolation:
            raise HTTPException(status_code=404, detail="Child or device not found") from None
        except DuplicateConflict:
            raise HTTPException(status_code=409, detail="Session replay conflicts with stored data") from None
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error)) from None

    @router.get("/children/{child_id}/daily-safety-report")
    def daily_safety_report(
        child_id: str,
        family_id: Annotated[str, Depends(current_family_id)],
        report_date: Annotated[date, Query(alias="date")],
        timezone: str = "UTC",
    ) -> object:
        try:
            return service.daily_safety_report(family_id, child_id, report_date, timezone)
        except ScopeViolation:
            raise HTTPException(status_code=404, detail="Child not found") from None
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error)) from None

    @router.get("/settings")
    def family_settings(family_id: Annotated[str, Depends(current_family_id)]) -> object:
        return service.family_settings(family_id)

    @router.patch("/settings/retention")
    def update_retention(
        payload: RetentionUpdateInput,
        family_id: Annotated[str, Depends(current_family_id)],
    ) -> object:
        try:
            return service.update_retention(
                family_id,
                payload.retention_days,
                changed_at=clock(),
            )
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error)) from None

    @router.patch("/settings/notification-channels")
    def update_notification_channels(
        payload: NotificationChannelsInput,
        family_id: Annotated[str, Depends(current_family_id)],
    ) -> object:
        try:
            settings = service.update_notification_channels(
                family_id,
                payload.channels,
                changed_at=clock(),
            )
            if notification_channels_changed is not None:
                notification_channels_changed(family_id, settings.notification_channels)
            return settings
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error)) from None

    @router.post("/support-cases", status_code=status.HTTP_201_CREATED)
    def open_support_case(
        payload: SupportCaseInput,
        family_id: Annotated[str, Depends(current_family_id)],
    ) -> object:
        try:
            return service.open_support_case(
                family_id,
                kind=payload.kind,
                summary=payload.summary,
                child_id=payload.child_id,
                incident_id=payload.incident_id,
                evidence_ids=payload.evidence_ids,
                evidence_consent=payload.evidence_consent,
                submitted_at=clock(),
            )
        except ScopeViolation:
            raise HTTPException(status_code=404, detail="Related resource not found") from None
        except EvidenceConsentRequired:
            raise HTTPException(
                status_code=422,
                detail="Explicit consent is required before sharing evidence",
            ) from None
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error)) from None

    @router.get("/support-cases/{case_id}")
    def support_case(
        case_id: str,
        family_id: Annotated[str, Depends(current_family_id)],
    ) -> object:
        try:
            return service.support_case(family_id, case_id)
        except ScopeViolation:
            raise HTTPException(status_code=404, detail="Support case not found") from None

    return router
