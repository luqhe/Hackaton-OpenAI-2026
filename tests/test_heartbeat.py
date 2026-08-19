from fastapi.testclient import TestClient

from api.main import create_app
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


def test_healthy_heartbeat_marks_device_protected_and_updates_last_seen(tmp_path) -> None:
    app = create_app(tmp_path / "guardian.db", tmp_path / "evidence")
    with TestClient(app) as client:
        response = client.post("/api/devices/device-demo/heartbeat", json=heartbeat())

    assert response.status_code == 200
    assert response.json()["protection_status"] == "PROTECTED"
    assert response.json()["last_seen_at"] is not None


def test_missing_permission_marks_device_degraded(tmp_path) -> None:
    app = create_app(tmp_path / "guardian.db", tmp_path / "evidence")
    with TestClient(app) as client:
        response = client.post(
            "/api/devices/device-demo/heartbeat",
            json=heartbeat(accessibility_permission=False),
        )

    assert response.status_code == 200
    assert response.json()["protection_status"] == "DEGRADED"


def test_heartbeat_rejects_unknown_device_and_unbounded_queue(tmp_path) -> None:
    app = create_app(tmp_path / "guardian.db", tmp_path / "evidence")
    with TestClient(app) as client:
        missing = client.post("/api/devices/missing/heartbeat", json=heartbeat())
        invalid = client.post(
            "/api/devices/device-demo/heartbeat",
            json=heartbeat(offline_queue_depth=1001),
        )

    assert missing.status_code == 404
    assert invalid.status_code == 422
