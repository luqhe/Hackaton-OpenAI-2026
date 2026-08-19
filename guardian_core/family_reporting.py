"""Tenant-scoped family reporting, settings and privacy-minimized support contracts.

The module consumes R1 session events and R2 identity/authorization facts through
an adapter. It neither classifies content nor creates device commands.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, replace
from datetime import UTC, date, datetime, time, timedelta
from enum import StrEnum
from typing import Protocol
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


class ScopeViolation(Exception):
    """A resource does not exist in the authenticated family scope."""


class DuplicateConflict(Exception):
    """An idempotency key was replayed with different content."""


class EvidenceConsentRequired(Exception):
    """Evidence cannot be shared with support without explicit consent."""


class SafetyMetric(StrEnum):
    RISK_EVENTS = "risk_events"
    GUARDIAN_ALERTS = "guardian_alerts"
    POLICY_INTERVENTIONS = "policy_interventions"
    CONTESTATIONS = "contestations"


class DataStatus(StrEnum):
    AVAILABLE = "AVAILABLE"
    NO_DATA = "NO_DATA"
    SYNC_PENDING = "SYNC_PENDING"


class RetentionKind(StrEnum):
    EVIDENCE = "evidence"
    INCIDENT_METADATA = "incident_metadata"
    SUPPORT_MESSAGE = "support_message"


class NotificationChannel(StrEnum):
    IN_APP = "in_app"
    EMAIL = "email"
    PUSH = "push"


class CaseKind(StrEnum):
    SUPPORT = "SUPPORT"
    FEEDBACK = "FEEDBACK"
    MISCLASSIFICATION = "MISCLASSIFICATION"


@dataclass(frozen=True)
class DeviceSummary:
    device_id: str
    display_name: str


@dataclass(frozen=True)
class ChildSummary:
    child_id: str
    display_name: str
    devices: tuple[DeviceSummary, ...]


@dataclass(frozen=True)
class SessionSafetyEvent:
    event_id: str
    occurred_at: datetime
    metric: SafetyMetric
    count: int = 1

    def __post_init__(self) -> None:
        if not self.event_id.strip():
            raise ValueError("Safety event id is required")
        if self.occurred_at.tzinfo is None:
            raise ValueError("Safety event timestamp must include a timezone")
        if not isinstance(self.metric, SafetyMetric):
            raise ValueError("Only declared safety metrics are accepted")
        if not 1 <= self.count <= 1_000_000:
            raise ValueError("Safety event count is outside the supported range")


@dataclass(frozen=True)
class SessionUpload:
    child_id: str
    device_id: str
    source_event_id: str
    source: str
    started_at: datetime
    ended_at: datetime
    safety_events: tuple[SessionSafetyEvent, ...] = ()
    captured_offline: bool = False

    def __post_init__(self) -> None:
        if self.source != "OBSERVER_SESSION":
            raise ValueError("Only real observer sessions are accepted")
        if self.started_at.tzinfo is None or self.ended_at.tzinfo is None:
            raise ValueError("Session timestamps must include a timezone")
        if self.ended_at <= self.started_at:
            raise ValueError("Session end must be later than its start")
        event_ids = {event.event_id for event in self.safety_events}
        if len(event_ids) != len(self.safety_events):
            raise ValueError("Safety event ids must be unique within a session")
        if any(
            event.occurred_at < self.started_at or event.occurred_at > self.ended_at
            for event in self.safety_events
        ):
            raise ValueError("Safety events must occur within their observer session")


@dataclass(frozen=True)
class StoredSession:
    family_id: str
    upload: SessionUpload
    synced_at: datetime


@dataclass(frozen=True)
class SessionReceipt:
    source_event_id: str
    deduplicated: bool


@dataclass(frozen=True)
class DailySafetyReport:
    child_id: str
    local_date: date
    timezone: str
    data_status: DataStatus
    metrics: dict[SafetyMetric, int]
    device_ids: tuple[str, ...]
    missing_device_ids: tuple[str, ...]
    offline_sync_received: bool
    classifier_controls_device: bool = False


@dataclass(frozen=True)
class FamilySettings:
    retention_days: dict[RetentionKind, int]
    notification_channels: frozenset[NotificationChannel]

    @property
    def channels(self) -> frozenset[NotificationChannel]:
        """Compatibility name used by notification adapters."""

        return self.notification_channels


@dataclass(frozen=True)
class RetainedRecord:
    family_id: str
    record_id: str
    kind: RetentionKind
    created_at: datetime
    expires_at: datetime


@dataclass(frozen=True)
class RetentionUpdate:
    settings: FamilySettings
    effective_for_new_records_at: datetime
    deletion_record_ids: tuple[str, ...]


@dataclass(frozen=True)
class AuditEvent:
    family_id: str
    kind: str
    occurred_at: datetime
    details: tuple[str, ...]


@dataclass(frozen=True)
class IncidentMetadata:
    family_id: str
    child_id: str
    incident_id: str
    classifier_version: str


@dataclass(frozen=True)
class SupportCase:
    case_id: str
    family_id: str
    child_id: str | None
    incident_id: str | None
    kind: CaseKind
    summary: str
    status: str
    submitted_at: datetime
    evidence_ids: tuple[str, ...]
    evidence_consent: bool
    access_roles: frozenset[str]
    classifier_version: str | None
    classifier_controls_device: bool = False


class FamilyScopePort(Protocol):
    """R2 adapter: authoritative family, child and device relationships."""

    def children_for_family(self, family_id: str) -> tuple[ChildSummary, ...]: ...

    def child_belongs_to_family(self, family_id: str, child_id: str) -> bool: ...

    def device_belongs_to_child(self, family_id: str, child_id: str, device_id: str) -> bool: ...


class SessionPort(Protocol):
    """R1/R2 adapter: idempotent observer-session persistence and sync coverage."""

    def session(self, device_id: str, source_event_id: str) -> StoredSession | None: ...

    def save_session(self, session: StoredSession) -> None: ...

    def sessions_for_child(self, family_id: str, child_id: str) -> tuple[StoredSession, ...]: ...

    def pending_devices(self, family_id: str, child_id: str, local_date: date) -> tuple[str, ...]: ...


class SettingsPort(Protocol):
    """R2 adapter: settings, expiry work and immutable audit persistence."""

    def settings(self, family_id: str) -> FamilySettings | None: ...

    def save_settings(self, family_id: str, settings: FamilySettings) -> None: ...

    def save_retained_record(self, record: RetainedRecord) -> None: ...

    def records(self, family_id: str, kind: RetentionKind) -> tuple[RetainedRecord, ...]: ...

    def append_audit(self, event: AuditEvent) -> None: ...


class SupportPort(Protocol):
    """R2/R3 adapter: scoped incident metadata and minimized case persistence."""

    def incident(self, incident_id: str) -> IncidentMetadata | None: ...

    def evidence_belongs_to_incident(self, evidence_id: str, incident_id: str) -> bool: ...

    def save_case(self, case: SupportCase) -> None: ...

    def case(self, case_id: str) -> SupportCase | None: ...


class FamilyReportingAdapter(FamilyScopePort, SessionPort, SettingsPort, SupportPort, Protocol):
    pass


class InMemoryFamilyReportingAdapter:
    """Process-local reference adapter for tests; not production persistence."""

    def __init__(self) -> None:
        self._children: dict[tuple[str, str], str] = {}
        self._devices: dict[str, tuple[str, str, str]] = {}
        self._sessions: dict[tuple[str, str], StoredSession] = {}
        self._pending: set[tuple[str, str, str, date]] = set()
        self._settings: dict[str, FamilySettings] = {}
        self.retained_records: dict[str, RetainedRecord] = {}
        self.audit_events: list[AuditEvent] = []
        self._incidents: dict[str, IncidentMetadata] = {}
        self._evidence: dict[str, str] = {}
        self._cases: dict[str, SupportCase] = {}

    def add_child(self, family_id: str, child_id: str, display_name: str) -> None:
        self._children[(family_id, child_id)] = display_name

    def add_device(self, family_id: str, child_id: str, device_id: str, display_name: str) -> None:
        if (family_id, child_id) not in self._children:
            raise ScopeViolation
        self._devices[device_id] = (family_id, child_id, display_name)

    def add_incident(
        self, family_id: str, child_id: str, incident_id: str, *, classifier_version: str
    ) -> None:
        if (family_id, child_id) not in self._children:
            raise ScopeViolation
        self._incidents[incident_id] = IncidentMetadata(family_id, child_id, incident_id, classifier_version)

    def add_evidence(self, incident_id: str, evidence_id: str) -> None:
        if incident_id not in self._incidents:
            raise ScopeViolation
        self._evidence[evidence_id] = incident_id

    def mark_sync_pending(self, family_id: str, child_id: str, device_id: str, local_date: date) -> None:
        if not self.device_belongs_to_child(family_id, child_id, device_id):
            raise ScopeViolation
        self._pending.add((family_id, child_id, device_id, local_date))

    def children_for_family(self, family_id: str) -> tuple[ChildSummary, ...]:
        result: list[ChildSummary] = []
        for (candidate_family, child_id), display_name in sorted(self._children.items()):
            if candidate_family != family_id:
                continue
            devices = tuple(
                DeviceSummary(device_id, values[2])
                for device_id, values in sorted(self._devices.items())
                if values[:2] == (family_id, child_id)
            )
            result.append(ChildSummary(child_id, display_name, devices))
        return tuple(result)

    def child_belongs_to_family(self, family_id: str, child_id: str) -> bool:
        return (family_id, child_id) in self._children

    def device_belongs_to_child(self, family_id: str, child_id: str, device_id: str) -> bool:
        values = self._devices.get(device_id)
        return values is not None and values[:2] == (family_id, child_id)

    def session(self, device_id: str, source_event_id: str) -> StoredSession | None:
        return self._sessions.get((device_id, source_event_id))

    def save_session(self, session: StoredSession) -> None:
        key = (session.upload.device_id, session.upload.source_event_id)
        self._sessions[key] = session

    def sessions_for_child(self, family_id: str, child_id: str) -> tuple[StoredSession, ...]:
        return tuple(
            session
            for session in self._sessions.values()
            if session.family_id == family_id and session.upload.child_id == child_id
        )

    def pending_devices(self, family_id: str, child_id: str, local_date: date) -> tuple[str, ...]:
        return tuple(
            sorted(
                device_id
                for pending_family, pending_child, device_id, pending_date in self._pending
                if (pending_family, pending_child, pending_date) == (family_id, child_id, local_date)
            )
        )

    def settings(self, family_id: str) -> FamilySettings | None:
        return self._settings.get(family_id)

    def save_settings(self, family_id: str, settings: FamilySettings) -> None:
        self._settings[family_id] = settings

    def save_retained_record(self, record: RetainedRecord) -> None:
        self.retained_records[record.record_id] = record

    def records(self, family_id: str, kind: RetentionKind) -> tuple[RetainedRecord, ...]:
        return tuple(
            record
            for record in self.retained_records.values()
            if record.family_id == family_id and record.kind is kind
        )

    def append_audit(self, event: AuditEvent) -> None:
        self.audit_events.append(event)

    def incident(self, incident_id: str) -> IncidentMetadata | None:
        return self._incidents.get(incident_id)

    def evidence_belongs_to_incident(self, evidence_id: str, incident_id: str) -> bool:
        return self._evidence.get(evidence_id) == incident_id

    def save_case(self, case: SupportCase) -> None:
        self._cases[case.case_id] = case

    def case(self, case_id: str) -> SupportCase | None:
        return self._cases.get(case_id)


class FamilyReportingService:
    """Application service for R4-18 through R4-22.

    The service returns reports and settings only. No method returns or issues a
    device command, keeping classification and enforcement structurally separate.
    """

    _DEFAULT_RETENTION = {
        RetentionKind.EVIDENCE: 7,
        RetentionKind.INCIDENT_METADATA: 30,
        RetentionKind.SUPPORT_MESSAGE: 30,
    }
    _RETENTION_BOUNDS = {
        RetentionKind.EVIDENCE: (1, 30),
        RetentionKind.INCIDENT_METADATA: (7, 90),
        RetentionKind.SUPPORT_MESSAGE: (7, 90),
    }

    def __init__(self, adapter: FamilyReportingAdapter):
        self._adapter = adapter

    def _require_child(self, family_id: str, child_id: str) -> None:
        if not self._adapter.child_belongs_to_family(family_id, child_id):
            raise ScopeViolation

    def _require_device(self, family_id: str, child_id: str, device_id: str) -> None:
        self._require_child(family_id, child_id)
        if not self._adapter.device_belongs_to_child(family_id, child_id, device_id):
            raise ScopeViolation

    def family_scope(self, family_id: str) -> tuple[ChildSummary, ...]:
        return self._adapter.children_for_family(family_id)

    def ingest_session(self, family_id: str, upload: SessionUpload, *, synced_at: datetime) -> SessionReceipt:
        self._require_device(family_id, upload.child_id, upload.device_id)
        if synced_at.tzinfo is None:
            raise ValueError("Sync timestamp must include a timezone")
        existing = self._adapter.session(upload.device_id, upload.source_event_id)
        if existing is not None:
            if existing.family_id != family_id or existing.upload != upload:
                raise DuplicateConflict
            return SessionReceipt(upload.source_event_id, deduplicated=True)
        prior_events = {
            (stored.upload.device_id, event.event_id): event
            for stored in self._adapter.sessions_for_child(family_id, upload.child_id)
            for event in stored.upload.safety_events
        }
        if any(
            prior_events.get((upload.device_id, event.event_id)) not in (None, event)
            for event in upload.safety_events
        ):
            raise DuplicateConflict
        self._adapter.save_session(StoredSession(family_id, upload, synced_at))
        return SessionReceipt(upload.source_event_id, deduplicated=False)

    def daily_safety_report(
        self, family_id: str, child_id: str, local_date: date, timezone: str
    ) -> DailySafetyReport:
        self._require_child(family_id, child_id)
        try:
            zone = ZoneInfo(timezone)
        except ZoneInfoNotFoundError as error:
            raise ValueError("Unknown IANA timezone") from error
        local_start = datetime.combine(local_date, time.min, tzinfo=zone)
        local_end = local_start + timedelta(days=1)
        start_utc = local_start.astimezone(UTC)
        end_utc = local_end.astimezone(UTC)
        sessions = tuple(
            session
            for session in self._adapter.sessions_for_child(family_id, child_id)
            if session.upload.started_at < end_utc and session.upload.ended_at >= start_utc
        )
        totals: dict[SafetyMetric, int] = {}
        seen_events: set[tuple[str, str]] = set()
        for session in sessions:
            for event in session.upload.safety_events:
                deduplication_key = (session.upload.device_id, event.event_id)
                if deduplication_key in seen_events:
                    continue
                if start_utc <= event.occurred_at < end_utc:
                    seen_events.add(deduplication_key)
                    totals[event.metric] = totals.get(event.metric, 0) + event.count
        pending = self._adapter.pending_devices(family_id, child_id, local_date)
        if pending:
            data_status = DataStatus.SYNC_PENDING
        elif sessions:
            data_status = DataStatus.AVAILABLE
        else:
            data_status = DataStatus.NO_DATA
        return DailySafetyReport(
            child_id=child_id,
            local_date=local_date,
            timezone=timezone,
            data_status=data_status,
            metrics=totals,
            device_ids=tuple(sorted({session.upload.device_id for session in sessions})),
            missing_device_ids=pending,
            offline_sync_received=any(session.upload.captured_offline for session in sessions),
        )

    def family_settings(self, family_id: str) -> FamilySettings:
        existing = self._adapter.settings(family_id)
        if existing is not None:
            return FamilySettings(dict(existing.retention_days), frozenset(existing.channels))
        defaults = FamilySettings(
            retention_days=dict(self._DEFAULT_RETENTION),
            notification_channels=frozenset({NotificationChannel.IN_APP}),
        )
        self._adapter.save_settings(family_id, defaults)
        return FamilySettings(dict(defaults.retention_days), frozenset(defaults.channels))

    def update_retention(
        self,
        family_id: str,
        requested_days: dict[RetentionKind, int],
        *,
        changed_at: datetime,
    ) -> RetentionUpdate:
        if changed_at.tzinfo is None:
            raise ValueError("Settings timestamp must include a timezone")
        current = self.family_settings(family_id)
        updated_days = dict(current.retention_days)
        deletion_ids: set[str] = set()
        changes: list[str] = []
        for kind, days in requested_days.items():
            if not isinstance(kind, RetentionKind):
                raise ValueError("Unknown retention kind")
            minimum, maximum = self._RETENTION_BOUNDS[kind]
            if not minimum <= days <= maximum:
                raise ValueError(f"{kind.value} retention must be between {minimum} and {maximum} days")
            previous = updated_days[kind]
            updated_days[kind] = days
            changes.append(f"{kind.value}:{previous}->{days}")
            if days >= previous:
                continue
            for record in self._adapter.records(family_id, kind):
                shortened = min(record.expires_at, record.created_at + timedelta(days=days))
                self._adapter.save_retained_record(replace(record, expires_at=shortened))
                if shortened <= changed_at:
                    deletion_ids.add(record.record_id)
        settings = FamilySettings(updated_days, current.channels)
        self._adapter.save_settings(family_id, settings)
        self._adapter.append_audit(
            AuditEvent(family_id, "retention_updated", changed_at, tuple(sorted(changes)))
        )
        return RetentionUpdate(settings, changed_at, tuple(sorted(deletion_ids)))

    def register_retained_record(
        self,
        family_id: str,
        *,
        record_id: str,
        kind: RetentionKind,
        created_at: datetime,
    ) -> RetainedRecord:
        if created_at.tzinfo is None:
            raise ValueError("Record timestamp must include a timezone")
        days = self.family_settings(family_id).retention_days[kind]
        record = RetainedRecord(
            family_id,
            record_id,
            kind,
            created_at,
            created_at + timedelta(days=days),
        )
        self._adapter.save_retained_record(record)
        return record

    def update_notification_channels(
        self,
        family_id: str,
        channels: frozenset[NotificationChannel],
        *,
        changed_at: datetime,
    ) -> FamilySettings:
        if NotificationChannel.IN_APP not in channels:
            raise ValueError("The essential in-app safety channel cannot be disabled")
        if any(not isinstance(channel, NotificationChannel) for channel in channels):
            raise ValueError("Unknown notification channel")
        current = self.family_settings(family_id)
        updated = FamilySettings(dict(current.retention_days), frozenset(channels))
        self._adapter.save_settings(family_id, updated)
        self._adapter.append_audit(
            AuditEvent(
                family_id,
                "notification_channels_updated",
                changed_at,
                tuple(sorted(channel.value for channel in channels)),
            )
        )
        return updated

    def open_support_case(
        self,
        family_id: str,
        *,
        kind: CaseKind,
        summary: str,
        submitted_at: datetime,
        child_id: str | None = None,
        incident_id: str | None = None,
        evidence_ids: tuple[str, ...] = (),
        evidence_consent: bool = False,
    ) -> SupportCase:
        minimized_summary = summary.strip()
        if not minimized_summary or len(minimized_summary) > 500:
            raise ValueError("Support summary must contain between 1 and 500 characters")
        if child_id is not None:
            self._require_child(family_id, child_id)
        incident_metadata = None
        if incident_id is not None:
            incident_metadata = self._adapter.incident(incident_id)
            if incident_metadata is None or incident_metadata.family_id != family_id:
                raise ScopeViolation
            if child_id is not None and incident_metadata.child_id != child_id:
                raise ScopeViolation
        if evidence_ids and not evidence_consent:
            raise EvidenceConsentRequired
        if evidence_ids and incident_metadata is None:
            raise ValueError("Evidence references require a scoped incident")
        if len(set(evidence_ids)) != len(evidence_ids) or len(evidence_ids) > 3:
            raise ValueError("At most three unique evidence references may be shared")
        if incident_id is not None and any(
            not self._adapter.evidence_belongs_to_incident(evidence_id, incident_id)
            for evidence_id in evidence_ids
        ):
            raise ScopeViolation
        roles = {"SUPPORT_TRIAGE"}
        if evidence_ids:
            roles.add("SAFETY_REVIEWER")
        status = (
            "SAFETY_TRIAGE"
            if kind is CaseKind.MISCLASSIFICATION and incident_metadata is not None
            else "OPEN"
        )
        case = SupportCase(
            case_id=f"case-{uuid.uuid4().hex[:16]}",
            family_id=family_id,
            child_id=child_id,
            incident_id=incident_id,
            kind=kind,
            summary=minimized_summary,
            status=status,
            submitted_at=submitted_at,
            evidence_ids=evidence_ids,
            evidence_consent=bool(evidence_ids and evidence_consent),
            access_roles=frozenset(roles),
            classifier_version=(
                incident_metadata.classifier_version if incident_metadata is not None else None
            ),
        )
        self._adapter.save_case(case)
        self._adapter.append_audit(
            AuditEvent(
                family_id,
                "support_case_created",
                submitted_at,
                (f"kind:{kind.value}", f"evidence_count:{len(evidence_ids)}"),
            )
        )
        return case

    def support_case(self, family_id: str, case_id: str) -> SupportCase:
        case = self._adapter.case(case_id)
        if case is None or case.family_id != family_id:
            raise ScopeViolation
        return case
