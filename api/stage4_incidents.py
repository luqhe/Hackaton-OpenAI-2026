from __future__ import annotations

from collections.abc import Callable
from dataclasses import asdict
from datetime import UTC, datetime
from typing import Literal

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field

from guardian_core.family_incidents import FamilyIncidentService


def _utc_now() -> datetime:
    return datetime.now(UTC)


class ContestationInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    contestation_id: str = Field(min_length=1, max_length=100)
    reason: str = Field(min_length=1, max_length=280)


class FamilyDecisionInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    decision_id: str = Field(min_length=1, max_length=100)
    outcome: Literal["UNLOCK", "KEEP_BLOCKED"]
    decided_at: datetime
    command_expires_at: datetime | None = None


class CommandResultInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    executed: bool
    failure_code: str | None = Field(default=None, max_length=80)


class UnlockRetryInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    retry_id: str = Field(min_length=1, max_length=100)
    requested_at: datetime
    expires_at: datetime


def build_stage4_router(
    service: FamilyIncidentService,
    *,
    clock: Callable[[], datetime] = _utc_now,
) -> APIRouter:
    """Compose Stage 4 HTTP endpoints around an injected domain service."""

    router = APIRouter()

    @router.get("/api/incidents/{incident_id}/experience")
    def incident_experience(incident_id: str) -> dict:
        try:
            return asdict(service.incident_view(incident_id, now=clock()))
        except KeyError:
            raise HTTPException(status_code=404, detail="Incident not found") from None

    @router.post(
        "/api/incidents/{incident_id}/contestations",
        status_code=status.HTTP_201_CREATED,
    )
    def submit_contestation(incident_id: str, payload: ContestationInput) -> dict:
        try:
            receipt = service.submit_contestation(
                incident_id,
                reason=payload.reason,
                submitted_at=clock(),
                contestation_id=payload.contestation_id,
            )
        except KeyError:
            raise HTTPException(status_code=404, detail="Incident not found") from None
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error)) from None
        return asdict(receipt)

    @router.post(
        "/api/incidents/{incident_id}/family-decisions",
        status_code=status.HTTP_202_ACCEPTED,
    )
    def submit_family_decision(incident_id: str, payload: FamilyDecisionInput) -> dict:
        try:
            received_at = clock()
            receipt = service.submit_guardian_decision(
                incident_id,
                decision_id=payload.decision_id,
                outcome=payload.outcome,
                decided_at=received_at,
                command_expires_at=payload.command_expires_at,
            )
        except KeyError:
            raise HTTPException(status_code=404, detail="Incident not found") from None
        except ValueError as error:
            raise HTTPException(status_code=409, detail=str(error)) from None
        return asdict(receipt)

    @router.post(
        "/api/incidents/{incident_id}/unlock-retries",
        status_code=status.HTTP_202_ACCEPTED,
    )
    def retry_unlock(incident_id: str, payload: UnlockRetryInput) -> dict:
        try:
            command = service.retry_unlock(
                incident_id,
                retry_id=payload.retry_id,
                requested_at=payload.requested_at,
                expires_at=payload.expires_at,
            )
        except KeyError:
            raise HTTPException(status_code=404, detail="Incident not found") from None
        except ValueError as error:
            raise HTTPException(status_code=409, detail=str(error)) from None
        return asdict(command)

    @router.get("/api/devices/{device_id}/unlock-commands")
    def poll_unlock_commands(device_id: str) -> list[dict]:
        return [asdict(command) for command in service.poll_commands(device_id, now=clock())]

    @router.post("/api/devices/{device_id}/unlock-commands/{command_id}/result")
    def report_command_result(device_id: str, command_id: str, payload: CommandResultInput) -> dict:
        try:
            command = service.report_command_result(
                command_id,
                executed=payload.executed,
                failure_code=payload.failure_code,
                reported_at=clock(),
                device_id=device_id,
            )
        except KeyError:
            raise HTTPException(status_code=404, detail="Command not found") from None
        except ValueError as error:
            raise HTTPException(status_code=409, detail=str(error)) from None
        return asdict(command)

    return router
