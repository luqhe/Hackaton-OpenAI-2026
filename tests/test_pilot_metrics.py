import sqlite3
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from api.main import create_app
from guardian_core.models import RiskCategory
from guardian_core.pilot_metrics import (
    ClassificationOutcome,
    FamilyPilotSurvey,
    summarize_pilot_metrics,
)

ONBOARDING_OCCURRED_AT = datetime.now(UTC).isoformat()


def onboarding_payload(**overrides):
    payload = {
        "child_id": "child-demo",
        "device_id": "device-demo",
        "session_id": "session-pilot-0001",
        "stage": "STARTED",
        "occurred_at": ONBOARDING_OCCURRED_AT,
        "idempotency_key": "onboarding-pilot-0001-started",
    }
    payload.update(overrides)
    return payload


def incident_payload() -> dict:
    return {
        "child_id": "child-demo",
        "device_id": "device-demo",
        "application": "Guardian Demo Chat",
        "occurred_at": datetime.now(UTC).isoformat(),
        "assessment": {
            "risk": "HIGH",
            "category": "DANGEROUS_CONTACT",
            "direction": "CHILD_AS_TARGET",
            "confidence": 0.94,
            "evidence": ["age", "school"],
            "explanation": "Progressive personal-information requests were detected.",
        },
        "decision": {
            "action": "BLOCK",
            "matched_rule": {
                "category": "DANGEROUS_CONTACT",
                "action": "BLOCK",
                "minimum_risk": "HIGH",
                "minimum_confidence": 0.75,
            },
            "reason": "Parental policy matched",
        },
        "deduplication_key": "pilot-metrics-command-latency",
    }


def heartbeat(**overrides):
    payload = {
        "agent_version": "0.2.0",
        "screen_recording_permission": True,
        "accessibility_permission": True,
        "observer_healthy": True,
        "offline_queue_depth": 3,
        "observed_at": datetime.now(UTC).isoformat(),
    }
    payload.update(overrides)
    return payload


def test_onboarding_events_are_allowlisted_idempotent_and_aggregated(tmp_path) -> None:
    app = create_app(tmp_path / "guardian.db", tmp_path / "evidence")
    with TestClient(app) as client:
        created = client.post("/api/pilot/onboarding-events", json=onboarding_payload())
        duplicate = client.post("/api/pilot/onboarding-events", json=onboarding_payload())
        conflicting_retry = client.post(
            "/api/pilot/onboarding-events",
            json=onboarding_payload(stage="PRIVACY_REVIEWED"),
        )
        timestamp_mismatch = client.post(
            "/api/pilot/onboarding-events",
            json=onboarding_payload(
                occurred_at=(
                    datetime.fromisoformat(ONBOARDING_OCCURRED_AT) + timedelta(seconds=1)
                ).isoformat()
            ),
        )
        rejected_content = client.post(
            "/api/pilot/onboarding-events",
            json=onboarding_payload(
                idempotency_key="onboarding-pilot-with-content",
                visible_text="content must never enter funnel telemetry",
            ),
        )
        report = client.get("/api/pilot/metrics").json()

    assert created.status_code == 201
    assert duplicate.status_code == 200
    assert duplicate.headers["X-Guardian-Deduplicated"] == "true"
    assert duplicate.json()["id"] == created.json()["id"]
    assert conflicting_retry.status_code == 409
    assert timestamp_mismatch.status_code == 409
    assert rejected_content.status_code == 422
    started = next(stage for stage in report["onboarding"] if stage["stage"] == "STARTED")
    assert started == {"stage": "STARTED", "event_count": 1, "unique_sessions": 1}


def test_onboarding_event_rejects_unknown_or_mismatched_device(tmp_path) -> None:
    app = create_app(tmp_path / "guardian.db", tmp_path / "evidence")
    with TestClient(app) as client:
        unknown = client.post(
            "/api/pilot/onboarding-events",
            json=onboarding_payload(device_id="device-missing", idempotency_key="onboarding-unknown-device"),
        )

    assert unknown.status_code == 404


def test_onboarding_requires_canonical_monotonic_progression(tmp_path) -> None:
    app = create_app(tmp_path / "guardian.db", tmp_path / "evidence")
    base = datetime.now(UTC)
    stages = [
        "STARTED",
        "PRIVACY_REVIEWED",
        "CONSENT_RECORDED",
        "CHILD_PROFILE_CONFIGURED",
        "DEVICE_PAIRED",
        "PERMISSIONS_GRANTED",
        "FIRST_HEALTHY_HEARTBEAT",
        "SHADOW_READY",
    ]
    with TestClient(app) as client:
        direct_shadow = client.post(
            "/api/pilot/onboarding-events",
            json=onboarding_payload(
                session_id="session-direct-shadow",
                stage="SHADOW_READY",
                idempotency_key="direct-shadow-is-invalid",
                occurred_at=base.isoformat(),
            ),
        )
        far_future = client.post(
            "/api/pilot/onboarding-events",
            json=onboarding_payload(
                session_id="session-future-start",
                idempotency_key="future-start-is-invalid",
                occurred_at=(base + timedelta(days=3650)).isoformat(),
            ),
        )
        responses = []
        for index, stage in enumerate(stages):
            responses.append(
                client.post(
                    "/api/pilot/onboarding-events",
                    json=onboarding_payload(
                        session_id="session-canonical-0001",
                        stage=stage,
                        idempotency_key=f"canonical-stage-{index:02d}",
                        occurred_at=(base + timedelta(seconds=index)).isoformat(),
                    ),
                )
            )
        non_monotonic = client.post(
            "/api/pilot/onboarding-events",
            json=onboarding_payload(
                session_id="session-monotonic-0001",
                idempotency_key="monotonic-start-0001",
                occurred_at=base.isoformat(),
            ),
        )
        assert non_monotonic.status_code == 201
        non_monotonic = client.post(
            "/api/pilot/onboarding-events",
            json=onboarding_payload(
                session_id="session-monotonic-0001",
                stage="PRIVACY_REVIEWED",
                idempotency_key="monotonic-privacy-0001",
                occurred_at=(base - timedelta(seconds=1)).isoformat(),
            ),
        )

    assert direct_shadow.status_code == 409
    assert far_future.status_code == 422
    assert [response.status_code for response in responses] == [201] * len(stages)
    assert non_monotonic.status_code == 409


def test_heartbeat_health_and_command_ack_latency_are_reported(tmp_path) -> None:
    database = tmp_path / "guardian.db"
    app = create_app(database, tmp_path / "evidence")
    with TestClient(app) as client:
        assert client.post("/api/devices/device-demo/heartbeat", json=heartbeat()).status_code == 200
        assert (
            client.post(
                "/api/devices/device-demo/heartbeat",
                json=heartbeat(observer_healthy=False, offline_queue_depth=7),
            ).status_code
            == 200
        )
        incident = client.post("/api/incidents", json=incident_payload()).json()
        client.post(f"/api/incidents/{incident['id']}/unlock")
        command = client.get("/api/devices/device-demo/commands").json()[0]
        created_at = datetime.now(UTC) - timedelta(seconds=4)
        with sqlite3.connect(database) as connection:
            connection.execute(
                "UPDATE device_commands SET created_at = ? WHERE id = ?",
                (created_at.isoformat(), command["id"]),
            )
        client.post(f"/api/devices/device-demo/commands/{command['id']}/ack")
        report = client.get("/api/pilot/metrics").json()

    assert report["health_sample_count"] == 2
    assert report["healthy_health_sample_count"] == 1
    assert report["agent_health_percent"] == 50.0
    assert report["offline_queue_depth_max"] == 7
    assert report["heartbeat_age_max_seconds"] is not None
    assert report["command_ack_count"] == 1
    assert 3900 <= report["command_ack_latency_p50_ms"] <= 5000
    assert report["command_ack_latency_p95_ms"] == report["command_ack_latency_p50_ms"]
    assert report["command_ack_latency_max_ms"] == report["command_ack_latency_p50_ms"]


def test_empty_metrics_report_uses_null_instead_of_claiming_health(tmp_path) -> None:
    app = create_app(tmp_path / "guardian.db", tmp_path / "evidence")
    with TestClient(app) as client:
        report = client.get("/api/pilot/metrics").json()

    assert report["health_sample_count"] == 0
    assert report["agent_health_percent"] is None
    assert report["heartbeat_age_max_seconds"] is None
    assert report["command_ack_count"] == 0
    assert report["command_ack_latency_p95_ms"] is None
NOW = datetime(2026, 8, 20, 15, tzinfo=UTC)


def outcome(
    event_id: str,
    *,
    human_confirmed_risk: bool,
    contested: bool = False,
    cohort_id: str = "pilot-alert-a",
) -> ClassificationOutcome:
    return ClassificationOutcome(
        event_id=event_id,
        cohort_id=cohort_id,
        category=RiskCategory.DANGEROUS_CONTACT,
        model_flagged=True,
        human_reviewed=True,
        human_confirmed_risk=human_confirmed_risk,
        incident_shown=True,
        contested=contested,
    )


def surveys(count: int, *, cohort_id: str = "pilot-alert-a") -> list[FamilyPilotSurvey]:
    return [
        FamilyPilotSurvey(
            response_id=f"response-{index}",
            cohort_id=cohort_id,
            family_subject_digest=f"{index:064x}",
            submitted_at=NOW,
            intervention_comprehension=3 + index % 3,
            guardian_confidence=4,
        )
        for index in range(count)
    ]


def test_metrics_use_explicit_review_and_incident_denominators() -> None:
    summary = summarize_pilot_metrics(
        "pilot-alert-a",
        [
            outcome("confirmed", human_confirmed_risk=True),
            outcome("fp", human_confirmed_risk=False, contested=True),
        ],
        surveys(5),
    )

    assert summary.reviewed_flagged_events == 2
    assert summary.false_positives == 1
    assert summary.false_positive_rate == 0.5
    assert summary.incidents_shown == 2
    assert summary.contested_incidents == 1
    assert summary.contestation_rate == 0.5
    assert summary.intervention_comprehension_mean == 3.8
    assert summary.guardian_confidence_mean == 4
    assert summary.feedback_suppressed is False


def test_small_feedback_samples_are_suppressed() -> None:
    summary = summarize_pilot_metrics(
        "pilot-alert-a",
        [outcome("confirmed", human_confirmed_risk=True)],
        surveys(2),
    )

    assert summary.survey_responses == 2
    assert summary.intervention_comprehension_mean is None
    assert summary.guardian_confidence_mean is None
    assert summary.feedback_suppressed is True


def test_summary_isolated_by_cohort() -> None:
    summary = summarize_pilot_metrics(
        "pilot-alert-a",
        [
            outcome("in-scope", human_confirmed_risk=True),
            outcome("other", human_confirmed_risk=False, cohort_id="other-cohort"),
        ],
        surveys(5) + surveys(5, cohort_id="other-cohort"),
    )

    assert summary.classification_events == 1
    assert summary.survey_responses == 5
    assert summary.false_positives == 0


def test_feedback_contract_rejects_free_text_and_invalid_outcomes() -> None:
    with pytest.raises(ValidationError, match="Extra inputs"):
        FamilyPilotSurvey.model_validate({**surveys(1)[0].model_dump(mode="json"), "comment": "raw text"})

    with pytest.raises(ValidationError, match="requires incident_shown"):
        ClassificationOutcome.model_validate(
            {
                **outcome("bad", human_confirmed_risk=True).model_dump(mode="json"),
                "incident_shown": False,
                "contested": True,
            }
        )


def test_feedback_sample_floor_is_validated() -> None:
    with pytest.raises(ValueError, match="at least 2"):
        summarize_pilot_metrics("pilot-alert-a", [], [], minimum_feedback_sample=1)


def test_retries_do_not_inflate_events_responses_or_families() -> None:
    event = outcome("idempotent-event", human_confirmed_risk=False, contested=True)
    responses = surveys(5)
    summary = summarize_pilot_metrics(
        "pilot-alert-a",
        [event, event],
        responses + [responses[0]],
    )

    assert summary.classification_events == 1
    assert summary.false_positives == 1
    assert summary.contested_incidents == 1
    assert summary.survey_responses == 5
    assert summary.unique_families == 5


def test_only_latest_response_per_family_contributes_to_feedback() -> None:
    original = surveys(5)
    replacement = original[0].model_copy(
        update={
            "response_id": "response-0-newer",
            "submitted_at": NOW.replace(hour=16),
            "intervention_comprehension": 1,
            "guardian_confidence": 1,
        }
    )
    summary = summarize_pilot_metrics(
        "pilot-alert-a",
        [],
        original + [replacement],
    )

    assert summary.survey_responses == 5
    assert summary.unique_families == 5
    assert summary.intervention_comprehension_mean == 3.4
    assert summary.guardian_confidence_mean == 3.4


def test_conflicting_duplicate_event_is_rejected() -> None:
    event = outcome("conflict", human_confirmed_risk=True)
    conflicting = event.model_copy(update={"human_confirmed_risk": False})

    with pytest.raises(ValueError, match="Conflicting classification outcome"):
        summarize_pilot_metrics("pilot-alert-a", [event, conflicting], [])
