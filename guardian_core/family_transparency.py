"""Truthful, privacy-minimized contracts for the child's transparency view.

The module deliberately consumes heartbeat and capability facts supplied by other
layers. It does not observe a device, authenticate a family, classify content, or
execute commands.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum


class AgeBand(StrEnum):
    YOUNGER = "6-9"
    PRETEEN = "10-12"
    TEEN = "13-17"
    GENERAL = "general"


class CapabilityAvailability(StrEnum):
    IMPLEMENTED = "IMPLEMENTED"
    PLANNED = "PLANNED"
    UNAVAILABLE = "UNAVAILABLE"


class ProtectionStatus(StrEnum):
    ACTIVE = "ACTIVE"
    DEMO = "DEMO"
    INACTIVE = "INACTIVE"
    STALE = "STALE"
    ERROR = "ERROR"
    PERMISSION_REQUIRED = "PERMISSION_REQUIRED"


class SharedDataKind(StrEnum):
    INCIDENT_SUMMARY = "INCIDENT_SUMMARY"
    MINIMUM_EVIDENCE = "MINIMUM_EVIDENCE"
    DAILY_APP_USAGE = "DAILY_APP_USAGE"
    CHILD_EXPLANATION = "CHILD_EXPLANATION"


@dataclass(frozen=True, slots=True)
class CapabilityDisclosure:
    key: str
    availability: CapabilityAvailability
    action_enabled: bool


@dataclass(frozen=True, slots=True)
class Heartbeat:
    received_at: datetime
    permissions_valid: bool = True
    error_code: str | None = None

    def __post_init__(self) -> None:
        _require_aware(self.received_at, "received_at")


@dataclass(frozen=True, slots=True)
class ProtectionState:
    status: ProtectionStatus
    is_active: bool
    checked_at: datetime
    heartbeat_at: datetime | None


@dataclass(frozen=True, slots=True)
class SharedDataRecord:
    record_id: str
    category: str
    shared_at: datetime
    recipient: str
    data_kinds: tuple[SharedDataKind, ...]

    def __post_init__(self) -> None:
        _require_aware(self.shared_at, "shared_at")
        if not self.record_id.strip() or not self.category.strip() or not self.recipient.strip():
            raise ValueError("share metadata fields cannot be empty")
        normalized: list[SharedDataKind] = []
        for kind in self.data_kinds:
            try:
                normalized.append(SharedDataKind(kind))
            except ValueError as error:
                if str(kind).upper() == "LIVE_SCREEN":
                    raise ValueError("live screen is never valid shared-data metadata") from error
                raise ValueError(f"unsupported shared data kind: {kind}") from error
        if not normalized:
            raise ValueError("at least one shared data kind is required")
        object.__setattr__(self, "data_kinds", tuple(normalized))


@dataclass(frozen=True, slots=True)
class ChildTransparencySnapshot:
    protection: ProtectionState
    capabilities: tuple[CapabilityDisclosure, ...]
    shared_records: tuple[SharedDataRecord, ...]
    age_band: AgeBand
    classifier_controls_device: bool = False
    live_screen_shared: bool = False


def normalize_age_band(value: str | AgeBand | None) -> AgeBand:
    """Return a supported content band without requiring an exact birth date."""

    try:
        return AgeBand(value)
    except (TypeError, ValueError):
        return AgeBand.GENERAL


def build_capability_disclosures(
    capabilities: Mapping[str, object], *, planned: Iterable[str] = ()
) -> tuple[CapabilityDisclosure, ...]:
    """Separate runtime facts from explicit plans; false never becomes implemented."""

    planned_keys = frozenset(planned)
    disclosures: list[CapabilityDisclosure] = []
    for key, implemented in capabilities.items():
        if type(implemented) is not bool:
            continue
        if implemented is True:
            availability = CapabilityAvailability.IMPLEMENTED
        elif key in planned_keys:
            availability = CapabilityAvailability.PLANNED
        else:
            availability = CapabilityAvailability.UNAVAILABLE
        disclosures.append(
            CapabilityDisclosure(
                key=key,
                availability=availability,
                action_enabled=availability is CapabilityAvailability.IMPLEMENTED,
            )
        )
    return tuple(disclosures)


def evaluate_protection(
    capabilities: Mapping[str, bool],
    heartbeat: Heartbeat | None,
    *,
    now: datetime | None = None,
    stale_after: timedelta = timedelta(minutes=3),
) -> ProtectionState:
    """Derive the visible state. Configuration alone never proves protection."""

    checked_at = now or datetime.now(UTC)
    _require_aware(checked_at, "now")
    if stale_after <= timedelta(0):
        raise ValueError("stale_after must be positive")

    if capabilities.get("real_screen_observation") is not True:
        return ProtectionState(ProtectionStatus.DEMO, False, checked_at, _heartbeat_time(heartbeat))
    if heartbeat is None:
        return ProtectionState(ProtectionStatus.INACTIVE, False, checked_at, None)
    if heartbeat.error_code:
        return ProtectionState(ProtectionStatus.ERROR, False, checked_at, heartbeat.received_at)
    if not heartbeat.permissions_valid:
        return ProtectionState(ProtectionStatus.PERMISSION_REQUIRED, False, checked_at, heartbeat.received_at)

    age = checked_at - heartbeat.received_at
    if age < -timedelta(minutes=1):
        return ProtectionState(ProtectionStatus.ERROR, False, checked_at, heartbeat.received_at)
    if age > stale_after:
        return ProtectionState(ProtectionStatus.STALE, False, checked_at, heartbeat.received_at)
    return ProtectionState(ProtectionStatus.ACTIVE, True, checked_at, heartbeat.received_at)


def build_transparency_snapshot(
    *,
    capabilities: Mapping[str, bool],
    planned: Iterable[str],
    heartbeat: Heartbeat | None,
    shared_records: Iterable[SharedDataRecord],
    age_band: str | AgeBand | None,
    now: datetime | None = None,
) -> ChildTransparencySnapshot:
    """Build the API-ready transparency snapshot from already-authorized metadata."""

    return ChildTransparencySnapshot(
        protection=evaluate_protection(capabilities, heartbeat, now=now),
        capabilities=build_capability_disclosures(capabilities, planned=planned),
        shared_records=tuple(shared_records),
        age_band=normalize_age_band(age_band),
    )


def _heartbeat_time(heartbeat: Heartbeat | None) -> datetime | None:
    return heartbeat.received_at if heartbeat else None


def _require_aware(value: datetime, field: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field} must include a timezone")
