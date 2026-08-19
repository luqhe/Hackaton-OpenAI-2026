from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient

from api.main import create_app
from guardian_core.config import Environment, GuardianSettings, LogLevel
from guardian_core.version import APP_VERSION


def heartbeat(**overrides):
    payload = {
        "agent_version": APP_VERSION,
        "screen_recording_permission": True,
        "accessibility_permission": True,
        "observer_healthy": True,
        "offline_queue_depth": 0,
    }
    payload.update(overrides)
    return payload


def demo_settings(tmp_path) -> GuardianSettings:
    return GuardianSettings(
        environment=Environment.TEST,
        database_path=tmp_path / "guardian.db",
        evidence_directory=tmp_path / "evidence",
        api_url="http://testserver",
        log_level=LogLevel.INFO,
        automatic_blocking_enabled=False,
        real_enforcement_enabled=False,
        release_gate_approved=False,
        demo_mode=True,
    )


def test_healthy_heartbeat_marks_device_protected_and_updates_last_seen(tmp_path) -> None:
    app = create_app(settings=demo_settings(tmp_path))
    with TestClient(app, headers={"X-Guardian-Demo": "true"}) as client:
        response = client.post("/api/devices/device-demo/heartbeat", json=heartbeat())

    assert response.status_code == 200
    assert response.json()["protection_status"] == "PROTECTED"
    assert response.json()["last_seen_at"] is not None


def test_missing_permission_marks_device_degraded(tmp_path) -> None:
    app = create_app(settings=demo_settings(tmp_path))
    with TestClient(app, headers={"X-Guardian-Demo": "true"}) as client:
        response = client.post(
            "/api/devices/device-demo/heartbeat",
            json=heartbeat(accessibility_permission=False),
        )

    assert response.status_code == 200
    assert response.json()["protection_status"] == "DEGRADED"


def test_heartbeat_rejects_unknown_device_and_unbounded_queue(tmp_path) -> None:
    app = create_app(settings=demo_settings(tmp_path))
    with TestClient(app, headers={"X-Guardian-Demo": "true"}) as client:
        missing = client.post("/api/devices/missing/heartbeat", json=heartbeat())
        invalid = client.post(
            "/api/devices/device-demo/heartbeat",
            json=heartbeat(offline_queue_depth=1001),
        )

    assert missing.status_code == 404
    assert invalid.status_code == 422


def test_heartbeat_presence_uses_server_time_and_degrades_when_stale(tmp_path) -> None:
    app = create_app(settings=demo_settings(tmp_path))
    with TestClient(app, headers={"X-Guardian-Demo": "true"}) as client:
        response = client.post(
            "/api/devices/device-demo/heartbeat",
            json=heartbeat(observed_at="2099-08-19T18:00:00Z"),
        )
        assert response.status_code == 200
        assert datetime.fromisoformat(response.json()["last_seen_at"]) < datetime.now(UTC) + timedelta(
            minutes=1
        )

        with app.state.store.connect() as connection:
            connection.execute(
                "UPDATE devices SET last_seen_at = ?, protection_status = 'PROTECTED' WHERE id = ?",
                ((datetime.now(UTC) - timedelta(minutes=10)).isoformat(), "device-demo"),
            )

        stale = client.get("/api/devices/device-demo")

    assert stale.status_code == 200
    assert stale.json()["protection_status"] == "DEGRADED"
