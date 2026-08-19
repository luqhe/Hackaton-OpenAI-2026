from __future__ import annotations

import re
from collections.abc import Callable
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field, field_validator

from guardian_core.family_experience import (
    AccountFamily,
    AgeBand,
    ChildProfile,
    ConsentRecord,
    ConsentVersionError,
    DependencyOfflineError,
    DuplicateAccountError,
    FamilyExperienceService,
    InvalidHeartbeatError,
    PairedDevice,
    PairingChallenge,
    PairingCodeExpiredError,
    PairingCodeInvalidError,
    PermissionName,
    PermissionState,
    PrivacyNotice,
    ProtectionSnapshot,
    ResourceNotFoundError,
)
from guardian_core.models import RiskCategory


class SignupRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: str = Field(min_length=3, max_length=254)
    family_name: str = Field(min_length=1, max_length=120)

    @field_validator("email")
    @classmethod
    def validate_email(cls, value: str) -> str:
        normalized = value.strip().casefold()
        if not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", normalized):
            raise ValueError("Invalid email address")
        return normalized


class ChildRegistrationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    display_name: str = Field(min_length=1, max_length=80)
    age_band: AgeBand
    requested_block_categories: set[RiskCategory] = Field(default_factory=set, max_length=4)


class PrivacyConsentRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    notice_version: str = Field(min_length=1, max_length=40)


class PairingStartRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    device_name: str = Field(min_length=1, max_length=120)


class PairingRedeemRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str = Field(min_length=8, max_length=8)

    @field_validator("code")
    @classmethod
    def validate_code(cls, value: str) -> str:
        normalized = value.strip().upper()
        if not re.fullmatch(r"[A-HJ-NP-Z2-9]{8}", normalized):
            raise ValueError("Invalid pairing code format")
        return normalized


class HeartbeatRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    observed_at: datetime
    agent_version: str = Field(min_length=1, max_length=80)
    permissions: dict[PermissionName, PermissionState]


def create_stage4_onboarding_router(
    service: FamilyExperienceService,
    *,
    authorize: Callable[[], None] | None = None,
) -> APIRouter:
    dependencies = [Depends(authorize)] if authorize is not None else []
    router = APIRouter(
        prefix="/api/onboarding",
        tags=["family-onboarding"],
        dependencies=dependencies,
    )

    @router.post("/families", response_model=AccountFamily, status_code=status.HTTP_201_CREATED)
    def create_family(payload: SignupRequest) -> AccountFamily:
        try:
            return service.create_account_and_family(
                email=payload.email,
                family_name=payload.family_name,
            )
        except DuplicateAccountError:
            raise HTTPException(status_code=409, detail="Account already exists") from None

    @router.get("/privacy-notice", response_model=PrivacyNotice)
    def privacy_notice() -> PrivacyNotice:
        return service.privacy_notice()

    @router.post(
        "/families/{family_id}/privacy-consent",
        response_model=ConsentRecord,
        status_code=status.HTTP_201_CREATED,
    )
    def accept_privacy_notice(family_id: str, payload: PrivacyConsentRequest) -> ConsentRecord:
        try:
            return service.accept_privacy_notice(
                family_id=family_id,
                notice_version=payload.notice_version,
            )
        except ConsentVersionError:
            raise HTTPException(
                status_code=409,
                detail="Privacy notice version is no longer current",
            ) from None
        except ResourceNotFoundError:
            raise HTTPException(status_code=404, detail="Family not found") from None

    @router.post(
        "/families/{family_id}/children",
        response_model=ChildProfile,
        status_code=status.HTTP_201_CREATED,
    )
    def register_child(family_id: str, payload: ChildRegistrationRequest) -> ChildProfile:
        try:
            return service.register_child(
                family_id=family_id,
                display_name=payload.display_name,
                age_band=payload.age_band,
                requested_block_categories=payload.requested_block_categories,
            )
        except ResourceNotFoundError:
            raise HTTPException(status_code=404, detail="Family not found") from None

    @router.post(
        "/families/{family_id}/children/{child_id}/pairing",
        response_model=PairingChallenge,
        status_code=status.HTTP_201_CREATED,
    )
    def start_pairing(family_id: str, child_id: str, payload: PairingStartRequest) -> PairingChallenge:
        try:
            return service.start_pairing(
                family_id=family_id,
                child_id=child_id,
                device_name=payload.device_name,
            )
        except ResourceNotFoundError:
            raise HTTPException(status_code=404, detail="Child not found in family") from None
        except DependencyOfflineError:
            raise HTTPException(
                status_code=503,
                detail="Pairing service temporarily unavailable",
            ) from None

    @router.post(
        "/pairing/{pairing_id}/retry",
        response_model=PairingChallenge,
        status_code=status.HTTP_201_CREATED,
    )
    def retry_pairing(pairing_id: str) -> PairingChallenge:
        try:
            return service.retry_pairing(pairing_id=pairing_id)
        except ResourceNotFoundError:
            raise HTTPException(status_code=404, detail="Pairing session not found") from None
        except PairingCodeInvalidError:
            raise HTTPException(status_code=409, detail="Pairing session already used") from None
        except DependencyOfflineError:
            raise HTTPException(
                status_code=503,
                detail="Pairing service temporarily unavailable",
            ) from None

    @router.post(
        "/pairing/redeem",
        response_model=PairedDevice,
        status_code=status.HTTP_201_CREATED,
    )
    def redeem_pairing(payload: PairingRedeemRequest) -> PairedDevice:
        try:
            return service.redeem_pairing(code=payload.code)
        except PairingCodeExpiredError:
            raise HTTPException(status_code=410, detail="Pairing code expired") from None
        except PairingCodeInvalidError:
            raise HTTPException(status_code=404, detail="Pairing code invalid") from None
        except DependencyOfflineError:
            raise HTTPException(
                status_code=503,
                detail="Pairing service temporarily unavailable",
            ) from None

    @router.get("/devices/{device_id}/protection", response_model=ProtectionSnapshot)
    def protection_status(device_id: str) -> ProtectionSnapshot:
        try:
            return service.protection_status(device_id=device_id)
        except ResourceNotFoundError:
            raise HTTPException(status_code=404, detail="Device not found") from None

    @router.post("/devices/{device_id}/heartbeat", response_model=ProtectionSnapshot)
    def record_heartbeat(device_id: str, payload: HeartbeatRequest) -> ProtectionSnapshot:
        try:
            return service.record_heartbeat(
                device_id=device_id,
                observed_at=payload.observed_at,
                agent_version=payload.agent_version,
                permissions=payload.permissions,
            )
        except ResourceNotFoundError:
            raise HTTPException(status_code=404, detail="Device not found") from None
        except InvalidHeartbeatError:
            raise HTTPException(status_code=422, detail="Heartbeat timestamp is invalid") from None

    return router
