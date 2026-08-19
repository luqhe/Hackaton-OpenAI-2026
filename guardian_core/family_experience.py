from __future__ import annotations

import hashlib
import secrets
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import Protocol, cast

from pydantic import BaseModel, ConfigDict, Field

from guardian_core.models import PolicyAction, RiskCategory


class FamilyExperienceError(Exception):
    """Base error safe to translate at the transport boundary."""


class DuplicateAccountError(FamilyExperienceError):
    pass


class ResourceNotFoundError(FamilyExperienceError):
    pass


class ConsentVersionError(FamilyExperienceError):
    pass


class PairingCodeExpiredError(FamilyExperienceError):
    pass


class PairingCodeInvalidError(FamilyExperienceError):
    pass


class DependencyOfflineError(FamilyExperienceError):
    pass


class InvalidHeartbeatError(FamilyExperienceError):
    pass


class AgeBand(StrEnum):
    CHILD_6_TO_9 = "6_TO_9"
    PRETEEN_10_TO_12 = "10_TO_12"
    TEEN_13_TO_17 = "13_TO_17"


class LanguageVariant(StrEnum):
    CHILD = "CHILD"
    PRETEEN = "PRETEEN"
    TEEN = "TEEN"


class InitialPolicyRule(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    category: RiskCategory
    action: PolicyAction
    blocking_gate_approved: bool


class ChildProfile(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    child_id: str
    family_id: str
    display_name: str
    age_band: AgeBand
    language_variant: LanguageVariant
    initial_policy: list[InitialPolicyRule]
    created_at: datetime


class PrivacyNotice(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    version: str
    collected: list[str]
    not_collected: list[str]
    retention_days: dict[str, int]
    access: list[str]
    boundaries: list[str]


class ConsentRecord(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    family_id: str
    notice_version: str
    accepted_at: datetime


class ProtectionStatus(StrEnum):
    PENDING = "PENDING"
    PROTECTED = "PROTECTED"
    DEGRADED = "DEGRADED"


class PermissionName(StrEnum):
    SCREEN_RECORDING = "SCREEN_RECORDING"
    ACCESSIBILITY = "ACCESSIBILITY"
    AUTOMATION = "AUTOMATION"


class PermissionState(StrEnum):
    UNKNOWN = "UNKNOWN"
    GRANTED = "GRANTED"
    DENIED = "DENIED"
    REVOKED = "REVOKED"


class PairingChallenge(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    pairing_id: str
    code: str = Field(min_length=8, max_length=8, repr=False)
    expires_at: datetime
    attempt: int = Field(ge=1)


class PairedDevice(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    device_id: str
    family_id: str
    child_id: str
    device_name: str
    platform: str
    paired_at: datetime
    protection_status: ProtectionStatus = ProtectionStatus.PENDING


class DeviceHealth(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    device_id: str
    observed_at: datetime
    agent_version: str
    permissions: dict[PermissionName, PermissionState]


class ProtectionSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    device_id: str
    status: ProtectionStatus
    reason: str
    last_heartbeat_at: datetime | None
    stale_after_seconds: int
    permissions: dict[PermissionName, PermissionState]


class AccountFamily(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    account_id: str
    family_id: str
    family_name: str
    created_at: datetime


class FamilyIdentityGateway(Protocol):
    """Adapter seam for R2 account, family and tenant-aware persistence."""

    def create_account_and_family(
        self, *, email: str, family_name: str, created_at: datetime
    ) -> AccountFamily: ...

    def family_exists(self, family_id: str) -> bool: ...

    def child_belongs_to_family(self, *, child_id: str, family_id: str) -> bool: ...

    def create_child(
        self,
        *,
        family_id: str,
        display_name: str,
        age_band: AgeBand,
        language_variant: LanguageVariant,
        initial_policy: list[InitialPolicyRule],
        created_at: datetime,
    ) -> ChildProfile: ...

    def record_privacy_consent(
        self, *, family_id: str, notice_version: str, accepted_at: datetime
    ) -> ConsentRecord: ...


class DevicePairingGateway(Protocol):
    """Adapter seam for R2 short-code exchange and device identity issuance."""

    def start_pairing(
        self,
        *,
        family_id: str,
        child_id: str,
        device_name: str,
        now: datetime,
        expires_at: datetime,
    ) -> PairingChallenge: ...

    def retry_pairing(self, *, pairing_id: str, now: datetime, expires_at: datetime) -> PairingChallenge: ...

    def redeem_pairing(self, *, code: str, now: datetime) -> PairedDevice: ...


class DeviceHealthGateway(Protocol):
    """Adapter seam for R1 heartbeat and permission observations."""

    def device_exists(self, device_id: str) -> bool: ...

    def record_device_health(self, health: DeviceHealth) -> None: ...

    def get_device_health(self, device_id: str) -> DeviceHealth | None: ...


@dataclass
class _PairingRecord:
    pairing_id: str
    code_digest: str
    family_id: str
    child_id: str
    device_name: str
    expires_at: datetime
    attempt: int
    redeemed: bool = False


class InMemoryFamilyExperienceAdapter:
    """Process-local fallback for tests and demos; it is not production persistence."""

    def __init__(self) -> None:
        self._families_by_email: dict[str, AccountFamily] = {}
        self._families_by_id: dict[str, AccountFamily] = {}
        self._children: dict[str, ChildProfile] = {}
        self._consents: dict[str, ConsentRecord] = {}
        self._pairings: dict[str, _PairingRecord] = {}
        self._devices: dict[str, PairedDevice] = {}
        self._device_health: dict[str, DeviceHealth] = {}
        self._pairing_available = True

    def create_account_and_family(
        self, *, email: str, family_name: str, created_at: datetime
    ) -> AccountFamily:
        normalized_email = email.strip().casefold()
        if normalized_email in self._families_by_email:
            raise DuplicateAccountError
        result = AccountFamily(
            account_id=f"account-{uuid.uuid4().hex}",
            family_id=f"family-{uuid.uuid4().hex}",
            family_name=family_name.strip(),
            created_at=created_at,
        )
        self._families_by_email[normalized_email] = result
        self._families_by_id[result.family_id] = result
        return result

    def family_exists(self, family_id: str) -> bool:
        return family_id in self._families_by_id

    def child_belongs_to_family(self, *, child_id: str, family_id: str) -> bool:
        child = self._children.get(child_id)
        return child is not None and child.family_id == family_id

    def create_child(
        self,
        *,
        family_id: str,
        display_name: str,
        age_band: AgeBand,
        language_variant: LanguageVariant,
        initial_policy: list[InitialPolicyRule],
        created_at: datetime,
    ) -> ChildProfile:
        if not self.family_exists(family_id):
            raise ResourceNotFoundError
        child = ChildProfile(
            child_id=f"child-{uuid.uuid4().hex}",
            family_id=family_id,
            display_name=display_name.strip(),
            age_band=age_band,
            language_variant=language_variant,
            initial_policy=initial_policy,
            created_at=created_at,
        )
        self._children[child.child_id] = child
        return child

    def record_privacy_consent(
        self, *, family_id: str, notice_version: str, accepted_at: datetime
    ) -> ConsentRecord:
        if not self.family_exists(family_id):
            raise ResourceNotFoundError
        record = ConsentRecord(
            family_id=family_id,
            notice_version=notice_version,
            accepted_at=accepted_at,
        )
        self._consents[family_id] = record
        return record

    def set_pairing_available(self, available: bool) -> None:
        self._pairing_available = available

    @staticmethod
    def _new_pairing_code() -> str:
        alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
        return "".join(secrets.choice(alphabet) for _ in range(8))

    @staticmethod
    def _code_digest(code: str) -> str:
        return hashlib.sha256(code.encode("ascii")).hexdigest()

    def _require_pairing_available(self) -> None:
        if not self._pairing_available:
            raise DependencyOfflineError

    def start_pairing(
        self,
        *,
        family_id: str,
        child_id: str,
        device_name: str,
        now: datetime,
        expires_at: datetime,
    ) -> PairingChallenge:
        self._require_pairing_available()
        code = self._new_pairing_code()
        pairing_id = f"pairing-{uuid.uuid4().hex}"
        record = _PairingRecord(
            pairing_id=pairing_id,
            code_digest=self._code_digest(code),
            family_id=family_id,
            child_id=child_id,
            device_name=device_name.strip(),
            expires_at=expires_at,
            attempt=1,
        )
        self._pairings[pairing_id] = record
        return PairingChallenge(
            pairing_id=pairing_id,
            code=code,
            expires_at=expires_at,
            attempt=record.attempt,
        )

    def retry_pairing(self, *, pairing_id: str, now: datetime, expires_at: datetime) -> PairingChallenge:
        self._require_pairing_available()
        record = self._pairings.get(pairing_id)
        if record is None:
            raise ResourceNotFoundError
        if record.redeemed:
            raise PairingCodeInvalidError
        code = self._new_pairing_code()
        record.code_digest = self._code_digest(code)
        record.expires_at = expires_at
        record.attempt += 1
        return PairingChallenge(
            pairing_id=pairing_id,
            code=code,
            expires_at=expires_at,
            attempt=record.attempt,
        )

    def redeem_pairing(self, *, code: str, now: datetime) -> PairedDevice:
        self._require_pairing_available()
        digest = self._code_digest(code.strip().upper())
        record = next(
            (candidate for candidate in self._pairings.values() if candidate.code_digest == digest),
            None,
        )
        if record is None or record.redeemed:
            raise PairingCodeInvalidError
        if now >= record.expires_at:
            raise PairingCodeExpiredError
        record.redeemed = True
        device = PairedDevice(
            device_id=f"device-{uuid.uuid4().hex}",
            family_id=record.family_id,
            child_id=record.child_id,
            device_name=record.device_name,
            platform="macOS",
            paired_at=now,
        )
        self._devices[device.device_id] = device
        return device

    def device_exists(self, device_id: str) -> bool:
        return device_id in self._devices

    def record_device_health(self, health: DeviceHealth) -> None:
        if not self.device_exists(health.device_id):
            raise ResourceNotFoundError
        self._device_health[health.device_id] = health

    def get_device_health(self, device_id: str) -> DeviceHealth | None:
        if not self.device_exists(device_id):
            raise ResourceNotFoundError
        return self._device_health.get(device_id)


class FamilyExperienceService:
    CURRENT_PRIVACY_NOTICE = PrivacyNotice(
        version="2026-08-19.1",
        collected=[
            "account_contact",
            "child_display_name_and_age_band",
            "technical_device_health",
            "minimal_incident_evidence_when_policy_triggers",
        ],
        not_collected=[
            "exact_birth_date",
            "continuous_live_screen",
            "camera",
            "microphone",
        ],
        retention_days={"technical_health": 30, "incident_evidence": 30},
        access=["authorized_family_members", "authorized_support_when_requested"],
        boundaries=[
            "classification_never_controls_the_device",
            "protection_requires_recent_agent_health_and_valid_permissions",
            "retention_requires_the_R2_data_lifecycle_adapter",
        ],
    )

    def __init__(
        self,
        *,
        adapter: FamilyIdentityGateway,
        approved_block_categories: set[str] | set[RiskCategory] | None = None,
        device_gateway: DevicePairingGateway | None = None,
        health_gateway: DeviceHealthGateway | None = None,
        now: Callable[[], datetime] | None = None,
        pairing_ttl: timedelta = timedelta(minutes=10),
        heartbeat_ttl: timedelta = timedelta(minutes=2),
    ) -> None:
        self._adapter = adapter
        self._device_gateway = device_gateway or cast(DevicePairingGateway, adapter)
        self._health_gateway = health_gateway or cast(DeviceHealthGateway, adapter)
        self._now = now or (lambda: datetime.now(UTC))
        self._pairing_ttl = pairing_ttl
        self._heartbeat_ttl = heartbeat_ttl
        self._approved_block_categories = {
            RiskCategory(category) for category in (approved_block_categories or set())
        }

    def create_account_and_family(self, *, email: str, family_name: str) -> AccountFamily:
        return self._adapter.create_account_and_family(
            email=email,
            family_name=family_name,
            created_at=self._now(),
        )

    def register_child(
        self,
        *,
        family_id: str,
        display_name: str,
        age_band: AgeBand,
        requested_block_categories: set[RiskCategory] | None = None,
    ) -> ChildProfile:
        if not self._adapter.family_exists(family_id):
            raise ResourceNotFoundError
        requested_blocks = requested_block_categories or set()
        age_defaults = {
            AgeBand.CHILD_6_TO_9: {category: PolicyAction.ALERT for category in RiskCategory},
            AgeBand.PRETEEN_10_TO_12: {
                RiskCategory.ADULT_CONTENT: PolicyAction.ALERT,
                RiskCategory.HATE_SPEECH: PolicyAction.ALERT,
                RiskCategory.DANGEROUS_CONTACT: PolicyAction.ALERT,
                RiskCategory.OTHER: PolicyAction.ALLOW,
            },
            AgeBand.TEEN_13_TO_17: {
                RiskCategory.ADULT_CONTENT: PolicyAction.ALLOW,
                RiskCategory.HATE_SPEECH: PolicyAction.ALLOW,
                RiskCategory.DANGEROUS_CONTACT: PolicyAction.ALERT,
                RiskCategory.OTHER: PolicyAction.ALLOW,
            },
        }
        policy = [
            InitialPolicyRule(
                category=category,
                action=(
                    PolicyAction.BLOCK
                    if category in requested_blocks and category in self._approved_block_categories
                    else PolicyAction.ALERT
                    if category in requested_blocks
                    else age_defaults[age_band][category]
                ),
                blocking_gate_approved=category in self._approved_block_categories,
            )
            for category in RiskCategory
        ]
        variants = {
            AgeBand.CHILD_6_TO_9: LanguageVariant.CHILD,
            AgeBand.PRETEEN_10_TO_12: LanguageVariant.PRETEEN,
            AgeBand.TEEN_13_TO_17: LanguageVariant.TEEN,
        }
        return self._adapter.create_child(
            family_id=family_id,
            display_name=display_name,
            age_band=age_band,
            language_variant=variants[age_band],
            initial_policy=policy,
            created_at=self._now(),
        )

    def privacy_notice(self) -> PrivacyNotice:
        return self.CURRENT_PRIVACY_NOTICE

    def accept_privacy_notice(self, *, family_id: str, notice_version: str) -> ConsentRecord:
        if notice_version != self.CURRENT_PRIVACY_NOTICE.version:
            raise ConsentVersionError
        if not self._adapter.family_exists(family_id):
            raise ResourceNotFoundError
        return self._adapter.record_privacy_consent(
            family_id=family_id,
            notice_version=notice_version,
            accepted_at=self._now(),
        )

    def start_pairing(self, *, family_id: str, child_id: str, device_name: str) -> PairingChallenge:
        if not self._adapter.child_belongs_to_family(child_id=child_id, family_id=family_id):
            raise ResourceNotFoundError
        now = self._now()
        return self._device_gateway.start_pairing(
            family_id=family_id,
            child_id=child_id,
            device_name=device_name,
            now=now,
            expires_at=now + self._pairing_ttl,
        )

    def retry_pairing(self, *, pairing_id: str) -> PairingChallenge:
        now = self._now()
        return self._device_gateway.retry_pairing(
            pairing_id=pairing_id,
            now=now,
            expires_at=now + self._pairing_ttl,
        )

    def redeem_pairing(self, *, code: str) -> PairedDevice:
        return self._device_gateway.redeem_pairing(code=code, now=self._now())

    @staticmethod
    def _unknown_permissions() -> dict[PermissionName, PermissionState]:
        return {permission: PermissionState.UNKNOWN for permission in PermissionName}

    def protection_status(self, *, device_id: str) -> ProtectionSnapshot:
        if not self._health_gateway.device_exists(device_id):
            raise ResourceNotFoundError
        health = self._health_gateway.get_device_health(device_id)
        if health is None:
            return ProtectionSnapshot(
                device_id=device_id,
                status=ProtectionStatus.PENDING,
                reason="awaiting_first_heartbeat",
                last_heartbeat_at=None,
                stale_after_seconds=int(self._heartbeat_ttl.total_seconds()),
                permissions=self._unknown_permissions(),
            )

        permissions = self._unknown_permissions()
        permissions.update(health.permissions)
        if self._now() - health.observed_at > self._heartbeat_ttl:
            status = ProtectionStatus.DEGRADED
            reason = "heartbeat_stale"
        elif any(state != PermissionState.GRANTED for state in permissions.values()):
            status = ProtectionStatus.DEGRADED
            reason = "permissions_invalid"
        else:
            status = ProtectionStatus.PROTECTED
            reason = "agent_healthy"
        return ProtectionSnapshot(
            device_id=device_id,
            status=status,
            reason=reason,
            last_heartbeat_at=health.observed_at,
            stale_after_seconds=int(self._heartbeat_ttl.total_seconds()),
            permissions=permissions,
        )

    def record_heartbeat(
        self,
        *,
        device_id: str,
        observed_at: datetime,
        agent_version: str,
        permissions: dict[PermissionName, PermissionState],
    ) -> ProtectionSnapshot:
        if not self._health_gateway.device_exists(device_id):
            raise ResourceNotFoundError
        now = self._now()
        if observed_at.tzinfo is None or observed_at > now + timedelta(seconds=30):
            raise InvalidHeartbeatError
        self._health_gateway.record_device_health(
            DeviceHealth(
                device_id=device_id,
                observed_at=observed_at,
                agent_version=agent_version,
                permissions=permissions,
            )
        )
        return self.protection_status(device_id=device_id)
