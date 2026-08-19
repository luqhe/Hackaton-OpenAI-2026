import sqlite3
from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient

from api.main import create_app

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
