from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.stage4_family import create_stage4_family_router
from guardian_core.family_reporting import (
    CaseKind,
    DataStatus,
    DuplicateConflict,
    EvidenceConsentRequired,
    FamilyReportingService,
    InMemoryFamilyReportingAdapter,
    NotificationChannel,
    RetentionKind,
    SafetyMetric,
    ScopeViolation,
    SessionSafetyEvent,
    SessionUpload,
)

NOW = datetime(2026, 8, 19, 15, 0, tzinfo=UTC)


def make_service() -> tuple[FamilyReportingService, InMemoryFamilyReportingAdapter]:
    adapter = InMemoryFamilyReportingAdapter()
    adapter.add_child("family-a", "child-a", "Ana")
    adapter.add_device("family-a", "child-a", "device-a1", "Mac Ana")
    adapter.add_device("family-a", "child-a", "device-a2", "Mac reserva")
    adapter.add_child("family-a", "child-b", "Bia")
    adapter.add_device("family-a", "child-b", "device-b1", "Mac Bia")
    adapter.add_child("family-b", "child-x", "X")
    adapter.add_device("family-b", "child-x", "device-x1", "Mac X")
    adapter.add_incident("family-a", "child-a", "incident-a", classifier_version="model-7")
    adapter.add_incident("family-b", "child-x", "incident-x", classifier_version="model-9")
    return FamilyReportingService(adapter), adapter


def upload(
    *,
    child_id: str = "child-a",
    device_id: str = "device-a1",
    source_event_id: str = "session-1",
    started_at: datetime = datetime(2026, 8, 19, 13, 0, tzinfo=UTC),
    ended_at: datetime = datetime(2026, 8, 19, 14, 0, tzinfo=UTC),
    events: tuple[SessionSafetyEvent, ...] = (),
    captured_offline: bool = False,
) -> SessionUpload:
    return SessionUpload(
        child_id=child_id,
        device_id=device_id,
        source_event_id=source_event_id,
        source="OBSERVER_SESSION",
        started_at=started_at,
        ended_at=ended_at,
        safety_events=events,
        captured_offline=captured_offline,
    )


def test_family_scope_lists_multiple_children_and_only_their_devices() -> None:
    service, _ = make_service()

    scope = service.family_scope("family-a")

    assert [(child.child_id, [device.device_id for device in child.devices]) for child in scope] == [
        ("child-a", ["device-a1", "device-a2"]),
        ("child-b", ["device-b1"]),
    ]
    assert all(device.device_id != "device-x1" for child in scope for device in child.devices)


def test_session_ingest_rejects_cross_child_and_cross_family_devices() -> None:
    service, _ = make_service()

    with pytest.raises(ScopeViolation):
        service.ingest_session("family-a", upload(device_id="device-b1"), synced_at=NOW)
    with pytest.raises(ScopeViolation):
        service.ingest_session("family-a", upload(device_id="device-x1"), synced_at=NOW)
    with pytest.raises(ScopeViolation):
        service.daily_safety_report("family-a", "child-x", date(2026, 8, 19), "UTC")


def test_daily_report_uses_child_timezone_and_deduplicates_offline_replays() -> None:
    service, _ = make_service()
    event = SessionSafetyEvent(
        event_id="risk-1",
        occurred_at=datetime(2026, 8, 20, 2, 30, tzinfo=UTC),
        metric=SafetyMetric.RISK_EVENTS,
        count=1,
    )
    late_session = upload(
        started_at=datetime(2026, 8, 20, 2, 0, tzinfo=UTC),
        ended_at=datetime(2026, 8, 20, 3, 0, tzinfo=UTC),
        events=(event,),
        captured_offline=True,
    )

    first = service.ingest_session("family-a", late_session, synced_at=NOW + timedelta(days=1))
    replay = service.ingest_session("family-a", late_session, synced_at=NOW + timedelta(days=1, minutes=5))

    assert first.deduplicated is False
    assert replay.deduplicated is True
    sao_paulo = service.daily_safety_report("family-a", "child-a", date(2026, 8, 19), "America/Sao_Paulo")
    utc = service.daily_safety_report("family-a", "child-a", date(2026, 8, 19), "UTC")
    assert sao_paulo.metrics == {SafetyMetric.RISK_EVENTS: 1}
    assert sao_paulo.offline_sync_received is True
    assert utc.metrics == {}


def test_report_deduplicates_one_safety_event_rebatched_in_two_sessions() -> None:
    service, _ = make_service()
    repeated_event = SessionSafetyEvent(
        event_id="stable-observer-event-1",
        occurred_at=datetime(2026, 8, 19, 13, 30, tzinfo=UTC),
        metric=SafetyMetric.RISK_EVENTS,
    )
    service.ingest_session(
        "family-a",
        upload(source_event_id="batch-1", events=(repeated_event,)),
        synced_at=NOW,
    )
    service.ingest_session(
        "family-a",
        upload(source_event_id="batch-2", events=(repeated_event,)),
        synced_at=NOW,
    )

    report = service.daily_safety_report("family-a", "child-a", date(2026, 8, 19), "UTC")

    assert report.metrics == {SafetyMetric.RISK_EVENTS: 1}


def test_session_ingest_rejects_conflicting_reuse_of_a_safety_event_id() -> None:
    service, _ = make_service()
    first_event = SessionSafetyEvent(
        event_id="stable-observer-event-1",
        occurred_at=datetime(2026, 8, 19, 13, 30, tzinfo=UTC),
        metric=SafetyMetric.RISK_EVENTS,
    )
    conflicting_event = SessionSafetyEvent(
        event_id="stable-observer-event-1",
        occurred_at=datetime(2026, 8, 19, 13, 30, tzinfo=UTC),
        metric=SafetyMetric.GUARDIAN_ALERTS,
    )
    service.ingest_session(
        "family-a",
        upload(source_event_id="batch-1", events=(first_event,)),
        synced_at=NOW,
    )

    with pytest.raises(DuplicateConflict):
        service.ingest_session(
            "family-a",
            upload(source_event_id="batch-2", events=(conflicting_event,)),
            synced_at=NOW,
        )


def test_report_combines_scoped_devices_without_mixing_children() -> None:
    service, _ = make_service()
    service.ingest_session(
        "family-a",
        upload(
            source_event_id="a1",
            events=(
                SessionSafetyEvent(
                    event_id="alert-a1",
                    occurred_at=datetime(2026, 8, 19, 13, 30, tzinfo=UTC),
                    metric=SafetyMetric.GUARDIAN_ALERTS,
                ),
            ),
        ),
        synced_at=NOW,
    )
    service.ingest_session(
        "family-a",
        upload(
            device_id="device-a2",
            source_event_id="a2",
            ended_at=datetime(2026, 8, 19, 15, 0, tzinfo=UTC),
            events=(
                SessionSafetyEvent(
                    event_id="alert-a2",
                    occurred_at=datetime(2026, 8, 19, 14, 30, tzinfo=UTC),
                    metric=SafetyMetric.GUARDIAN_ALERTS,
                    count=2,
                ),
            ),
        ),
        synced_at=NOW,
    )
    service.ingest_session(
        "family-a",
        upload(child_id="child-b", device_id="device-b1", source_event_id="b1"),
        synced_at=NOW,
    )

    report = service.daily_safety_report("family-a", "child-a", date(2026, 8, 19), "UTC")

    assert report.metrics == {SafetyMetric.GUARDIAN_ALERTS: 3}
    assert report.device_ids == ("device-a1", "device-a2")


def test_no_session_data_and_pending_offline_sync_are_explicit() -> None:
    service, adapter = make_service()

    no_data = service.daily_safety_report("family-a", "child-a", date(2026, 8, 18), "UTC")
    adapter.mark_sync_pending("family-a", "child-a", "device-a2", date(2026, 8, 18))
    pending = service.daily_safety_report("family-a", "child-a", date(2026, 8, 18), "UTC")

    assert no_data.data_status is DataStatus.NO_DATA
    assert no_data.metrics == {}
    assert pending.data_status is DataStatus.SYNC_PENDING
    assert pending.missing_device_ids == ("device-a2",)


def test_report_contract_rejects_productivity_or_judgment_metrics() -> None:
    assert {metric.value for metric in SafetyMetric} == {
        "risk_events",
        "guardian_alerts",
        "policy_interventions",
        "contestations",
    }
    with pytest.raises(ValueError):
        SessionSafetyEvent(
            event_id="bad-1",
            occurred_at=NOW,
            metric="productivity_score",  # type: ignore[arg-type]
        )


def test_retention_defaults_are_minimal_bounded_and_audited() -> None:
    service, adapter = make_service()

    defaults = service.family_settings("family-a")
    changed = service.update_retention(
        "family-a",
        {RetentionKind.EVIDENCE: 3, RetentionKind.INCIDENT_METADATA: 14},
        changed_at=NOW,
    )

    assert defaults.retention_days == {
        RetentionKind.EVIDENCE: 7,
        RetentionKind.INCIDENT_METADATA: 30,
        RetentionKind.SUPPORT_MESSAGE: 30,
    }
    assert changed.settings.retention_days[RetentionKind.EVIDENCE] == 3
    assert changed.effective_for_new_records_at == NOW
    assert adapter.audit_events[-1].kind == "retention_updated"
    assert "family-a" not in adapter.audit_events[-1].details

    with pytest.raises(ValueError):
        service.update_retention("family-a", {RetentionKind.EVIDENCE: 0}, changed_at=NOW)
    with pytest.raises(ValueError):
        service.update_retention("family-a", {RetentionKind.EVIDENCE: 365}, changed_at=NOW)


def test_retention_changes_are_prospective_and_reductions_queue_due_deletion() -> None:
    service, adapter = make_service()
    old = service.register_retained_record(
        "family-a",
        record_id="evidence-old",
        kind=RetentionKind.EVIDENCE,
        created_at=NOW - timedelta(days=5),
    )
    reduction = service.update_retention("family-a", {RetentionKind.EVIDENCE: 3}, changed_at=NOW)
    new = service.register_retained_record(
        "family-a",
        record_id="evidence-new",
        kind=RetentionKind.EVIDENCE,
        created_at=NOW,
    )
    service.update_retention("family-a", {RetentionKind.EVIDENCE: 14}, changed_at=NOW)

    assert old.expires_at == NOW - timedelta(days=5) + timedelta(days=7)
    assert reduction.deletion_record_ids == ("evidence-old",)
    assert adapter.retained_records["evidence-new"].expires_at == new.expires_at
    assert new.expires_at == NOW + timedelta(days=3)


def test_notification_channels_default_to_in_app_and_require_safe_fallback() -> None:
    service, adapter = make_service()

    assert service.family_settings("family-a").channels == frozenset({NotificationChannel.IN_APP})
    updated = service.update_notification_channels(
        "family-a",
        frozenset({NotificationChannel.IN_APP, NotificationChannel.EMAIL}),
        changed_at=NOW,
    )

    assert updated.channels == frozenset({NotificationChannel.IN_APP, NotificationChannel.EMAIL})
    assert adapter.audit_events[-1].kind == "notification_channels_updated"
    with pytest.raises(ValueError):
        service.update_notification_channels(
            "family-a", frozenset({NotificationChannel.EMAIL}), changed_at=NOW
        )


def test_support_case_minimizes_data_and_never_attaches_evidence_by_default() -> None:
    service, _ = make_service()

    case = service.open_support_case(
        "family-a",
        kind=CaseKind.MISCLASSIFICATION,
        summary="A classificação parece incorreta.",
        child_id="child-a",
        incident_id="incident-a",
        submitted_at=NOW,
    )

    assert case.case_id.startswith("case-")
    assert case.status == "SAFETY_TRIAGE"
    assert case.evidence_ids == ()
    assert case.evidence_consent is False
    assert case.access_roles == frozenset({"SUPPORT_TRIAGE"})
    assert case.classifier_version == "model-7"
    assert case.classifier_controls_device is False


def test_misclassification_without_incident_opens_an_unlinked_minimized_case() -> None:
    service, _ = make_service()

    case = service.open_support_case(
        "family-a",
        kind=CaseKind.MISCLASSIFICATION,
        summary="A classificação precisa de revisão.",
        child_id="child-a",
        submitted_at=NOW,
    )

    assert case.status == "OPEN"
    assert case.incident_id is None
    assert case.classifier_version is None
    assert case.evidence_ids == ()


def test_support_evidence_requires_explicit_consent_and_minimal_access() -> None:
    service, adapter = make_service()
    adapter.add_evidence("incident-a", "evidence-1")

    with pytest.raises(EvidenceConsentRequired):
        service.open_support_case(
            "family-a",
            kind=CaseKind.MISCLASSIFICATION,
            summary="Revisem este caso.",
            child_id="child-a",
            incident_id="incident-a",
            evidence_ids=("evidence-1",),
            submitted_at=NOW,
        )

    case = service.open_support_case(
        "family-a",
        kind=CaseKind.MISCLASSIFICATION,
        summary="Revisem este caso.",
        child_id="child-a",
        incident_id="incident-a",
        evidence_ids=("evidence-1",),
        evidence_consent=True,
        submitted_at=NOW,
    )

    assert case.evidence_ids == ("evidence-1",)
    assert case.access_roles == frozenset({"SUPPORT_TRIAGE", "SAFETY_REVIEWER"})
    assert service.support_case("family-a", case.case_id).status == "SAFETY_TRIAGE"


def test_support_rejects_evidence_from_another_incident_scope() -> None:
    service, adapter = make_service()
    adapter.add_evidence("incident-x", "evidence-x")

    with pytest.raises(ScopeViolation):
        service.open_support_case(
            "family-a",
            kind=CaseKind.MISCLASSIFICATION,
            summary="Não compartilhar evidência de outra família.",
            child_id="child-a",
            incident_id="incident-a",
            evidence_ids=("evidence-x",),
            evidence_consent=True,
            submitted_at=NOW,
        )


def test_support_and_incident_lookup_cannot_cross_family_scope() -> None:
    service, _ = make_service()

    with pytest.raises(ScopeViolation):
        service.open_support_case(
            "family-a",
            kind=CaseKind.MISCLASSIFICATION,
            summary="Tentativa cruzada.",
            child_id="child-x",
            incident_id="incident-x",
            submitted_at=NOW,
        )


def test_http_router_uses_authenticated_family_dependency_not_client_family_input() -> None:
    service, _ = make_service()
    app = FastAPI()
    app.include_router(create_stage4_family_router(service, current_family_id=lambda: "family-a"))

    with TestClient(app) as client:
        scope = client.get("/api/family/scope")
        cross_family = client.get(
            "/api/family/children/child-x/daily-safety-report",
            params={"date": "2026-08-19", "timezone": "UTC"},
        )
        unsafe_metric = client.post(
            "/api/family/session-events",
            json={
                "child_id": "child-a",
                "device_id": "device-a1",
                "source_event_id": "session-http",
                "source": "OBSERVER_SESSION",
                "started_at": "2026-08-19T13:00:00Z",
                "ended_at": "2026-08-19T14:00:00Z",
                "safety_events": [
                    {
                        "event_id": "bad-http",
                        "occurred_at": "2026-08-19T13:30:00Z",
                        "metric": "screen_time_score",
                        "count": 1,
                    }
                ],
            },
        )

    assert scope.status_code == 200
    assert {child["child_id"] for child in scope.json()} == {"child-a", "child-b"}
    assert cross_family.status_code == 404
    assert unsafe_metric.status_code == 422


def test_http_settings_and_unlinked_support_contracts_are_minimized() -> None:
    service, _ = make_service()
    app = FastAPI()
    app.include_router(create_stage4_family_router(service, current_family_id=lambda: "family-a"))

    with TestClient(app) as client:
        settings = client.get("/api/family/settings")
        support = client.post(
            "/api/family/support-cases",
            json={
                "kind": "MISCLASSIFICATION",
                "summary": "A classificação precisa de revisão.",
                "child_id": "child-a",
            },
        )

    assert settings.status_code == 200
    assert settings.json()["notification_channels"] == ["in_app"]
    assert support.status_code == 201
    assert support.json()["status"] == "OPEN"
    assert support.json()["evidence_ids"] == []
