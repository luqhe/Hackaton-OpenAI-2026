from datetime import UTC, datetime, timedelta

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.stage4_incidents import build_stage4_router
from guardian_core.family_incidents import (
    AssessmentExplanation,
    EvidenceReference,
    FamilyIncidentService,
    NotificationOutbox,
    NotificationPreferences,
    PolicyExplanation,
)

NOW = datetime(2026, 8, 19, 15, 0, tzinfo=UTC)


def _service() -> FamilyIncidentService:
    return FamilyIncidentService()


def _open_incident(service: FamilyIncidentService, *, incident_id: str = "inc-1") -> None:
    service.open_incident(
        incident_id=incident_id,
        family_id="family-1",
        child_id="child-1",
        device_id="device-1",
        detected_at=NOW,
        assessment=AssessmentExplanation(
            risk="HIGH",
            category="DANGEROUS_CONTACT",
            confidence=0.94,
            signals=("pedido de idade", "pedido de foto"),
            classifier_version="classifier-7",
        ),
        policy=PolicyExplanation(
            action="BLOCK",
            rule="Bloquear contato perigoso",
            threshold=0.75,
            policy_version="family-policy-3",
        ),
        evidence=(
            EvidenceReference(
                evidence_id="ev-active",
                kind="screenshot_crop",
                captured_at=NOW,
                expires_at=NOW + timedelta(hours=1),
                locator="private://bucket/family-1/opaque-token",
            ),
            EvidenceReference(
                evidence_id="ev-expired",
                kind="text_excerpt",
                captured_at=NOW,
                expires_at=NOW + timedelta(minutes=5),
                locator="private://ev-expired",
            ),
            EvidenceReference(
                evidence_id="ev-missing",
                kind="screenshot_crop",
                captured_at=NOW,
                expires_at=NOW + timedelta(hours=1),
                locator=None,
            ),
        ),
    )


def test_timeline_is_auditable_and_evidence_states_are_honest() -> None:
    service = _service()
    _open_incident(service)
    service.record_event("inc-1", "later", NOW + timedelta(minutes=2), event_id="evt-z")
    service.record_event("inc-1", "earlier", NOW + timedelta(minutes=1), event_id="evt-a")

    view = service.incident_view("inc-1", now=NOW + timedelta(minutes=10))

    assert [event.kind for event in view.timeline] == ["detected", "earlier", "later"]
    assert [item.state for item in view.evidence] == ["available", "expired", "missing"]
    assert view.evidence[0].access_url == "/api/evidence/ev-active"
    assert view.evidence[1].access_url is None
    assert view.evidence[2].access_url is None
    assert all(not hasattr(item, "locator") for item in view.evidence)


def test_explanation_is_separated_and_child_contestation_is_minimized() -> None:
    service = _service()
    _open_incident(service)

    receipt = service.submit_contestation(
        "inc-1",
        reason="É uma conversa com alguém que conheço.",
        submitted_at=NOW + timedelta(minutes=1),
        contestation_id="contest-1",
    )
    view = service.incident_view("inc-1", now=NOW + timedelta(minutes=2))

    assert view.assessment.classifier_version == "classifier-7"
    assert view.policy.policy_version == "family-policy-3"
    assert view.assessment.signals == ("pedido de idade", "pedido de foto")
    assert view.policy.rule == "Bloquear contato perigoso"
    assert receipt.status == "submitted"
    assert receipt.reason_length == 38
    assert [event.kind for event in view.timeline] == ["detected", "contestation_submitted"]
    assert not hasattr(view.timeline[-1], "reason")

    retry = service.submit_contestation(
        "inc-1",
        reason="É uma conversa com alguém que conheço.",
        submitted_at=NOW + timedelta(minutes=2),
        contestation_id="contest-1",
    )
    assert retry == receipt
    assert [event.kind for event in service.incident_view("inc-1", now=NOW).timeline].count(
        "contestation_submitted"
    ) == 1

    with pytest.raises(ValueError, match="already exists"):
        service.submit_contestation(
            "inc-1",
            reason="Outro motivo.",
            submitted_at=NOW + timedelta(minutes=2),
            contestation_id="contest-1",
        )

    with pytest.raises(ValueError, match="at most 280"):
        service.submit_contestation(
            "inc-1",
            reason="x" * 281,
            submitted_at=NOW,
            contestation_id="contest-too-long",
        )


class _FailingNotificationAdapter:
    def deliver(self, notification) -> None:
        raise ConnectionError("provider unavailable")


class _CapturingNotificationAdapter:
    def __init__(self) -> None:
        self.delivered = []

    def deliver(self, notification) -> None:
        self.delivered.append(notification)


def test_notification_is_non_blocking_deduplicated_and_has_safe_fallback() -> None:
    outbox = NotificationOutbox()
    outbox.configure("family-1", NotificationPreferences(enabled=True, channel="email"))
    service = FamilyIncidentService(notifications=outbox)

    _open_incident(service)
    service.queue_guardian_notification("inc-1", queued_at=NOW)

    assert len(outbox.pending(now=NOW)) == 1
    outbox.deliver_pending({"email": _FailingNotificationAdapter()}, now=NOW)
    retry = outbox.pending(now=NOW + timedelta(minutes=1))
    assert len(retry) == 1
    assert retry[0].attempt_count == 1
    assert len(outbox.in_app("family-1")) == 1
    assert outbox.in_app("family-1")[0].message == "Há uma atualização de segurança para revisar."

    adapter = _CapturingNotificationAdapter()
    outbox.deliver_pending({"email": adapter}, now=NOW + timedelta(minutes=1))
    outbox.deliver_pending({"email": adapter}, now=NOW + timedelta(minutes=2))

    assert len(adapter.delivered) == 1
    serialized = repr(adapter.delivered[0])
    assert "DANGEROUS_CONTACT" not in serialized
    assert "pedido de idade" not in serialized
    assert "Guardian Demo Chat" not in serialized

    outbox.unsubscribe("family-1")
    service.queue_guardian_notification("inc-1", queued_at=NOW + timedelta(minutes=3))
    assert outbox.pending(now=NOW + timedelta(minutes=4)) == ()


def test_unlock_waits_offline_expires_and_only_confirms_reported_execution() -> None:
    service = _service()
    _open_incident(service)
    decision = service.submit_guardian_decision(
        "inc-1",
        decision_id="decision-unlock",
        outcome="UNLOCK",
        decided_at=NOW + timedelta(minutes=1),
        command_expires_at=NOW + timedelta(minutes=5),
    )
    command_id = decision.command_id
    assert command_id is not None

    service.set_device_online("device-1", online=False)
    assert service.poll_commands("device-1", now=NOW + timedelta(minutes=2)) == ()
    assert service.incident_view("inc-1", now=NOW).unlock.status == "requested"
    with pytest.raises(ValueError, match="must be delivered"):
        service.report_command_result(command_id, executed=True, reported_at=NOW + timedelta(minutes=2))

    service.set_device_online("device-1", online=True)
    assert service.poll_commands("device-1", now=NOW + timedelta(minutes=6)) == ()
    assert service.incident_view("inc-1", now=NOW).unlock.status == "expired"

    retry = service.retry_unlock(
        "inc-1",
        retry_id="retry-1",
        requested_at=NOW + timedelta(minutes=6),
        expires_at=NOW + timedelta(minutes=10),
    )
    assert retry.status == "requested"
    assert [
        command.status for command in service.poll_commands("device-1", now=NOW + timedelta(minutes=7))
    ] == ["delivered"]

    _open_incident(service, incident_id="inc-2")
    active = service.submit_guardian_decision(
        "inc-2",
        decision_id="decision-active",
        outcome="UNLOCK",
        decided_at=NOW + timedelta(minutes=7),
        command_expires_at=NOW + timedelta(minutes=12),
    )
    delivered = service.poll_commands("device-1", now=NOW + timedelta(minutes=8))
    assert [command.status for command in delivered] == ["delivered"]
    assert service.incident_view("inc-2", now=NOW).unlock.execution_confirmed is False

    service.report_command_result(
        active.command_id,
        executed=True,
        reported_at=NOW + timedelta(minutes=9),
    )
    unlock = service.incident_view("inc-2", now=NOW).unlock
    assert unlock.status == "executed"
    assert unlock.execution_confirmed is True


def test_concurrent_family_decision_has_arrival_independent_winner() -> None:
    def resolve(order: tuple[str, str]):
        service = _service()
        _open_incident(service)
        decisions = {
            "z": {
                "decision_id": "decision-z",
                "outcome": "UNLOCK",
                "decided_at": NOW + timedelta(minutes=1),
                "command_expires_at": NOW + timedelta(minutes=5),
            },
            "a": {
                "decision_id": "decision-a",
                "outcome": "KEEP_BLOCKED",
                "decided_at": NOW + timedelta(minutes=1),
                "command_expires_at": None,
            },
        }
        for key in order:
            service.submit_guardian_decision("inc-1", **decisions[key])
        return service.incident_view("inc-1", now=NOW)

    unlock_first = resolve(("z", "a"))
    blocked_first = resolve(("a", "z"))

    assert unlock_first.family_decision.winner_id == "decision-a"
    assert blocked_first.family_decision.winner_id == "decision-a"
    assert unlock_first.family_decision.outcome == "KEEP_BLOCKED"
    assert blocked_first.family_decision.outcome == "KEEP_BLOCKED"
    assert unlock_first.unlock.status == "cancelled"
    assert blocked_first.unlock is None


def test_decision_replay_cannot_change_content_or_create_an_expired_command() -> None:
    service = _service()
    _open_incident(service)
    service.submit_guardian_decision(
        "inc-1",
        decision_id="decision-stable",
        outcome="UNLOCK",
        decided_at=NOW + timedelta(minutes=1),
        command_expires_at=NOW + timedelta(minutes=5),
    )

    with pytest.raises(ValueError, match="different content"):
        service.submit_guardian_decision(
            "inc-1",
            decision_id="decision-stable",
            outcome="KEEP_BLOCKED",
            decided_at=NOW + timedelta(minutes=1),
            command_expires_at=None,
        )

    _open_incident(service, incident_id="inc-expired")
    with pytest.raises(ValueError, match="after the decision"):
        service.submit_guardian_decision(
            "inc-expired",
            decision_id="decision-expired",
            outcome="UNLOCK",
            decided_at=NOW + timedelta(minutes=5),
            command_expires_at=NOW + timedelta(minutes=4),
        )


def test_stage4_router_uses_server_receipt_time_for_family_decisions() -> None:
    service = _service()
    _open_incident(service)
    received_at = NOW + timedelta(minutes=2)
    app = FastAPI()
    app.include_router(build_stage4_router(service, clock=lambda: received_at))

    with TestClient(app) as client:
        response = client.post(
            "/api/incidents/inc-1/family-decisions",
            json={
                "decision_id": "decision-server-time",
                "outcome": "UNLOCK",
                "decided_at": (NOW - timedelta(days=30)).isoformat(),
                "command_expires_at": (NOW + timedelta(minutes=5)).isoformat(),
            },
        )
        view = client.get("/api/incidents/inc-1/experience").json()

    assert response.status_code == 202
    serialized = view["family_decision"]["decided_at"].replace("Z", "+00:00")
    assert datetime.fromisoformat(serialized) == received_at


def test_stage4_router_exposes_command_failure_without_premature_ack() -> None:
    service = _service()
    _open_incident(service)
    app = FastAPI()
    app.include_router(build_stage4_router(service, clock=lambda: NOW + timedelta(minutes=2)))

    with TestClient(app) as client:
        experience = client.get("/api/incidents/inc-1/experience")
        assert experience.status_code == 200
        assert experience.json()["classifier_controls_device"] is False
        assert experience.json()["assessment"]["classifier_version"] == "classifier-7"
        assert experience.json()["policy"]["policy_version"] == "family-policy-3"

        contested = client.post(
            "/api/incidents/inc-1/contestations",
            json={"contestation_id": "contest-api", "reason": "Conheço essa pessoa."},
        )
        assert contested.status_code == 201
        assert "reason" not in contested.json()

        decision = client.post(
            "/api/incidents/inc-1/family-decisions",
            json={
                "decision_id": "decision-api",
                "outcome": "UNLOCK",
                "decided_at": (NOW + timedelta(minutes=1)).isoformat(),
                "command_expires_at": (NOW + timedelta(minutes=5)).isoformat(),
            },
        )
        assert decision.status_code == 202
        command_id = decision.json()["command_id"]

        service.set_device_online("device-1", online=False)
        assert client.get("/api/devices/device-1/unlock-commands").json() == []
        premature = client.post(
            f"/api/devices/device-1/unlock-commands/{command_id}/result",
            json={"executed": True},
        )
        assert premature.status_code == 409

        service.set_device_online("device-1", online=True)
        delivered = client.get("/api/devices/device-1/unlock-commands").json()
        assert delivered[0]["status"] == "delivered"
        failed = client.post(
            f"/api/devices/device-1/unlock-commands/{command_id}/result",
            json={"executed": False, "failure_code": "app_not_running"},
        )
        assert failed.status_code == 200
        assert failed.json()["status"] == "failed"
        failed_view = client.get("/api/incidents/inc-1/experience").json()
        assert failed_view["unlock"]["execution_confirmed"] is False
        assert failed_view["unlock"]["failure_code"] == "app_not_running"

        retried = client.post(
            "/api/incidents/inc-1/unlock-retries",
            json={
                "retry_id": "retry-api",
                "requested_at": (NOW + timedelta(minutes=3)).isoformat(),
                "expires_at": (NOW + timedelta(minutes=6)).isoformat(),
            },
        )
        assert retried.status_code == 202
        assert retried.json()["status"] == "requested"

        final_view = client.get("/api/incidents/inc-1/experience").json()
        assert final_view["unlock"]["execution_confirmed"] is False
        assert final_view["unlock"]["status"] == "requested"
