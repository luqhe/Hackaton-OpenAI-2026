from datetime import UTC, datetime

from fastapi.testclient import TestClient

from api.main import create_app


def _incident_payload() -> dict:
    return {
        "child_id": "child-demo",
        "device_id": "device-demo",
        "application": "Guardian Demo Chat",
        "occurred_at": datetime(2026, 8, 19, 15, 0, tzinfo=UTC).isoformat(),
        "assessment": {
            "risk": "HIGH",
            "category": "DANGEROUS_CONTACT",
            "direction": "CHILD_AS_TARGET",
            "confidence": 0.94,
            "evidence": ["pedido de idade", "pedido de foto"],
            "explanation": "Pedidos progressivos de dados pessoais foram identificados.",
        },
        "decision": {
            "action": "BLOCK",
            "matched_rule": {
                "category": "DANGEROUS_CONTACT",
                "action": "BLOCK",
                "minimum_risk": "HIGH",
                "minimum_confidence": 0.75,
            },
            "reason": "Política familiar correspondente",
        },
        "deduplication_key": "stage4-integration-incident",
    }


def test_real_app_mounts_stage4_onboarding_and_incident_experience(tmp_path) -> None:
    app = create_app(tmp_path / "guardian.db", tmp_path / "evidence")

    with TestClient(app) as client:
        family = client.post(
            "/api/onboarding/families",
            json={"email": "parent@example.com", "family_name": "Família Silva"},
        )
        assert family.status_code == 201

        created = client.post("/api/incidents", json=_incident_payload())
        assert created.status_code == 201
        experience = client.get(f"/api/incidents/{created.json()['id']}/experience")
        assert experience.status_code == 200
        assert experience.json()["assessment"]["classifier_version"] == "deterministic-fixture-v1"
        assert experience.json()["policy"]["action"] == "BLOCK"
        assert experience.json()["classifier_controls_device"] is False


def test_family_experience_ui_routes_are_served_by_the_spa(tmp_path) -> None:
    app = create_app(tmp_path / "guardian.db", tmp_path / "evidence")

    with TestClient(app) as client:
        for route in ("/onboarding", "/family", "/support"):
            response = client.get(route)
            assert response.status_code == 200
            assert "Guardian" in response.text


def test_real_app_mounts_scoped_family_settings_reports_and_support(tmp_path) -> None:
    app = create_app(tmp_path / "guardian.db", tmp_path / "evidence")

    with TestClient(app) as client:
        scope = client.get("/api/family/scope")
        assert scope.status_code == 200
        assert scope.json() == [
            {
                "child_id": "child-demo",
                "display_name": "Lucas",
                "devices": [
                    {
                        "device_id": "device-demo",
                        "display_name": "MacBook Pro",
                    }
                ],
            }
        ]

        settings = client.get("/api/family/settings")
        assert settings.status_code == 200
        assert settings.json()["notification_channels"] == ["in_app"]

        report = client.get(
            "/api/family/children/child-demo/daily-safety-report",
            params={"date": "2026-08-19", "timezone": "America/Sao_Paulo"},
        )
        assert report.status_code == 200
        assert report.json()["data_status"] == "NO_DATA"

        support = client.post(
            "/api/family/support-cases",
            json={
                "kind": "MISCLASSIFICATION",
                "summary": "A classificação precisa de revisão.",
                "child_id": "child-demo",
            },
        )
        assert support.status_code == 201
        assert support.json()["evidence_ids"] == []
        assert support.json()["status"] == "OPEN"


def test_device_starts_pending_and_transparency_uses_real_heartbeat(tmp_path) -> None:
    app = create_app(tmp_path / "guardian.db", tmp_path / "evidence")

    with TestClient(app) as client:
        pending = client.get("/api/devices/device-demo")
        assert pending.json()["protection_status"] == "PENDING"

        before = client.get("/api/children/child-demo/transparency").json()
        assert before["heartbeat"] is None

        observed_at = "2026-08-19T15:00:00Z"
        heartbeat = client.post(
            "/api/devices/device-demo/heartbeat",
            json={
                "agent_version": "0.1.0",
                "screen_recording_permission": True,
                "accessibility_permission": True,
                "observer_healthy": True,
                "offline_queue_depth": 0,
                "observed_at": observed_at,
            },
        )
        assert heartbeat.status_code == 200

        after = client.get("/api/children/child-demo/transparency").json()
        assert after["heartbeat"] == {
            "receivedAt": "2026-08-19T15:00:00+00:00",
            "permissionsValid": True,
            "errorCode": None,
        }


def test_r1_telemetry_feeds_real_safety_report_without_duplicate_replays(tmp_path) -> None:
    app = create_app(tmp_path / "guardian.db", tmp_path / "evidence")
    payload = {
        "child_id": "child-demo",
        "observed_at": "2026-08-19T15:00:00Z",
        "screen_changes": 14,
        "media_sessions": 3,
        "suspicious_events": 2,
        "app_name": "Safari",
        "session_seconds": 120,
    }

    with TestClient(app) as client:
        assert client.post("/api/devices/device-demo/telemetry", json=payload).status_code == 204
        assert client.post("/api/devices/device-demo/telemetry", json=payload).status_code == 204
        report = client.get(
            "/api/family/children/child-demo/daily-safety-report",
            params={"date": "2026-08-19", "timezone": "America/Sao_Paulo"},
        )

    assert report.status_code == 200
    assert report.json()["data_status"] == "AVAILABLE"
    assert report.json()["metrics"] == {"risk_events": 2}
    assert "screen_time" not in str(report.json()).lower()
    assert report.json()["classifier_controls_device"] is False


def test_notification_opt_in_configures_sanitized_non_blocking_outbox(tmp_path) -> None:
    app = create_app(tmp_path / "guardian.db", tmp_path / "evidence")

    with TestClient(app) as client:
        preference = client.patch(
            "/api/family/settings/notification-channels",
            json={"channels": ["in_app", "email"]},
        )
        assert preference.status_code == 200
        created = client.post("/api/incidents", json=_incident_payload())
        assert created.status_code == 201

    queued = app.state.notification_outbox.pending(now=datetime(2026, 8, 19, 16, 0, tzinfo=UTC))
    assert len(queued) == 1
    assert queued[0].channel == "email"
    serialized = repr(queued[0])
    assert "DANGEROUS_CONTACT" not in serialized
    assert "Guardian Demo Chat" not in serialized
    assert "pedido de idade" not in serialized


def test_misclassification_case_links_only_incident_version_metadata(tmp_path) -> None:
    app = create_app(tmp_path / "guardian.db", tmp_path / "evidence")

    with TestClient(app) as client:
        incident = client.post("/api/incidents", json=_incident_payload()).json()
        support = client.post(
            "/api/family/support-cases",
            json={
                "kind": "MISCLASSIFICATION",
                "summary": "A classificação precisa de revisão.",
                "child_id": "child-demo",
                "incident_id": incident["id"],
                "evidence_ids": [],
                "evidence_consent": False,
            },
        )

    assert support.status_code == 201
    assert support.json()["status"] == "SAFETY_TRIAGE"
    assert support.json()["classifier_version"] == "deterministic-fixture-v1"
    assert support.json()["evidence_ids"] == []
    assert "pedido de idade" not in str(support.json()).lower()


def test_family_cannot_expand_blocking_without_an_explicit_release_gate(tmp_path) -> None:
    app = create_app(tmp_path / "guardian.db", tmp_path / "evidence")

    with TestClient(app) as client:
        rules = client.get("/api/children/child-demo/policy").json()
        other = next(rule for rule in rules if rule["category"] == "OTHER")
        assert other["action"] == "ALERT"
        other["action"] = "BLOCK"

        response = client.put("/api/children/child-demo/policy", json=rules)

    assert response.status_code == 409
    assert response.json()["detail"] == "Blocking requires an approved category release gate"
