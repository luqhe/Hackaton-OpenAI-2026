from datetime import UTC, datetime

from fastapi.testclient import TestClient

from api.main import create_app


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
            "evidence": ["age", "school", "photo"],
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
        "deduplication_key": "fixture-dangerous-contact-0001",
    }


def test_complete_incident_unlock_command_flow(tmp_path) -> None:
    app = create_app(tmp_path / "guardian.db", tmp_path / "evidence")
    with TestClient(app) as client:
        assert client.get("/api/health").status_code == 200

        created = client.post("/api/incidents", json=incident_payload())
        assert created.status_code == 201
        incident = created.json()
        assert incident["status"] == "BLOCKED"

        duplicate = client.post("/api/incidents", json=incident_payload())
        assert duplicate.status_code == 200
        assert duplicate.headers["X-Guardian-Deduplicated"] == "true"
        assert duplicate.json()["id"] == incident["id"]

        evidence = client.post(
            f"/api/incidents/{incident['id']}/evidence",
            content=b"Alex: how old are you?",
            headers={"Content-Type": "text/plain"},
        )
        assert evidence.status_code == 201
        assert client.get(evidence.json()["url"]).text == "Alex: how old are you?"
        repeated_evidence = client.post(
            f"/api/incidents/{incident['id']}/evidence",
            content=b"Alex: how old are you?",
            headers={"Content-Type": "text/plain"},
        )
        assert repeated_evidence.json()["id"] == evidence.json()["id"]

        requested = client.post(
            f"/api/incidents/{incident['id']}/request-unlock",
            json={"explanation": "E um amigo da escola."},
        )
        assert requested.status_code == 200
        assert requested.json()["status"] == "UNLOCK_REQUESTED"

        unlocked = client.post(f"/api/incidents/{incident['id']}/unlock")
        assert unlocked.status_code == 200
        assert unlocked.json()["status"] == "UNLOCKED"

        commands = client.get("/api/devices/device-demo/commands").json()
        assert len(commands) == 1
        assert commands[0]["type"] == "UNLOCK_APPLICATION"
        acknowledged = client.post(f"/api/devices/device-demo/commands/{commands[0]['id']}/ack")
        assert acknowledged.json()["status"] == "ACKNOWLEDGED"
        assert client.get("/api/devices/device-demo/commands").json() == []

        replay = client.post("/api/incidents", json=incident_payload())
        assert replay.status_code == 201
        assert replay.headers["X-Guardian-Deduplicated"] == "false"
        assert replay.json()["id"] != incident["id"]


def test_policy_and_daily_report(tmp_path) -> None:
    app = create_app(tmp_path / "guardian.db", tmp_path / "evidence")
    with TestClient(app) as client:
        rules = client.get("/api/children/child-demo/policy").json()
        assert len(rules) == 4
        rules[0]["action"] = "ALERT"
        saved = client.put("/api/children/child-demo/policy", json=rules)
        assert saved.status_code == 200

        telemetry = client.post(
            "/api/devices/device-demo/telemetry",
            json={
                "child_id": "child-demo",
                "screen_changes": 4,
                "suspicious_events": 1,
                "app_name": "Safari",
                "session_seconds": 120,
            },
        )
        assert telemetry.status_code == 204
        report = client.get("/api/daily-report").json()
        assert report["screen_changes"] == 4
        assert report["total_seconds"] == 120


def test_pilot_technical_telemetry_rejects_content_fields(tmp_path) -> None:
    app = create_app(tmp_path / "guardian.db", tmp_path / "evidence")
    with TestClient(app) as client:
        accepted = client.post(
            "/api/devices/device-demo/pilot-telemetry",
            json={"agent_version": "0.1.0", "permission_state": "GRANTED"},
        )
        rejected = client.post(
            "/api/devices/device-demo/pilot-telemetry",
            json={"agent_version": "0.1.0", "visible_text": "private"},
        )

    assert accepted.status_code == 204
    assert rejected.status_code == 422


def test_safe_assessment_cannot_create_incident(tmp_path) -> None:
    app = create_app(tmp_path / "guardian.db", tmp_path / "evidence")
    payload = incident_payload()
    payload["assessment"] = {
        "risk": "SAFE",
        "category": None,
        "direction": None,
        "confidence": 0.9,
        "evidence": [],
        "explanation": "No risk.",
    }
    with TestClient(app) as client:
        response = client.post("/api/incidents", json=payload)
        assert response.status_code == 422
