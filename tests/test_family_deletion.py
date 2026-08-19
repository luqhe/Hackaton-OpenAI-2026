import sqlite3
from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from api.main import create_app
from scripts.delete_pilot_family import delete_with_confirmation


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
            "evidence": ["minimal signal"],
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
        "deduplication_key": "family-deletion-proof-0001",
    }


def seed_family_scope(client: TestClient) -> tuple[str, str]:
    incident = client.post("/api/incidents", json=incident_payload()).json()
    evidence = client.post(
        f"/api/incidents/{incident['id']}/evidence",
        content=b"minimal authorized evidence",
        headers={"Content-Type": "text/plain"},
    ).json()
    client.post(
        "/api/devices/device-demo/telemetry",
        json={
            "child_id": "child-demo",
            "screen_changes": 2,
            "app_name": "Safari",
            "session_seconds": 60,
        },
    )
    client.post(
        "/api/devices/device-demo/heartbeat",
        json={
            "agent_version": "0.2.0",
            "screen_recording_permission": True,
            "accessibility_permission": True,
            "observer_healthy": True,
            "offline_queue_depth": 0,
        },
    )
    client.post(
        "/api/pilot/onboarding-events",
        json={
            "child_id": "child-demo",
            "device_id": "device-demo",
            "session_id": "deletion-session-0001",
            "stage": "SHADOW_READY",
            "idempotency_key": "deletion-onboarding-proof-0001",
        },
    )
    client.post(f"/api/incidents/{incident['id']}/unlock")
    return incident["id"], evidence["id"]


def test_complete_family_deletion_covers_database_files_and_restart(tmp_path) -> None:
    database = tmp_path / "guardian.db"
    evidence_directory = tmp_path / "evidence"
    app = create_app(database, evidence_directory)
    with TestClient(app) as client:
        _, evidence_id = seed_family_scope(client)
        evidence_path, _ = app.state.store.get_evidence(evidence_id)
        receipt = delete_with_confirmation(app.state.store, "family-demo", "family-demo")

        assert receipt.status == "COMPLETED"
        assert receipt.completed_at is not None
        assert receipt.counts.families == 1
        assert receipt.counts.children == 1
        assert receipt.counts.devices == 1
        assert receipt.counts.policies == 4
        assert receipt.counts.incidents == 1
        assert receipt.counts.evidence_records == 1
        assert receipt.counts.evidence_files == 1
        assert receipt.counts.commands == 1
        assert receipt.counts.app_sessions == 1
        assert receipt.counts.daily_telemetry == 1
        assert receipt.counts.onboarding_events == 1
        assert receipt.counts.health_samples == 1
        assert not evidence_path.exists()
        assert client.get("/api/children/child-demo/policy").status_code == 404
        assert client.get("/api/devices/device-demo").status_code == 404

    with sqlite3.connect(database) as connection:
        for table in (
            "families",
            "children",
            "devices",
            "policies",
            "incidents",
            "incident_evidence",
            "device_commands",
            "app_sessions",
            "daily_telemetry",
            "pilot_onboarding_events",
            "agent_health_samples",
        ):
            assert connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] == 0
        row = connection.execute(
            "SELECT status, counts_json, staging_directory FROM family_deletion_receipts"
        ).fetchone()
        assert row[0] == "COMPLETED"
        assert "Lucas" not in row[1]
        assert "minimal authorized evidence" not in row[1]
        assert row[2] is None

    restarted = create_app(database, evidence_directory)
    with TestClient(restarted) as client:
        assert client.get("/api/children/child-demo/policy").status_code == 404
        metrics = client.get("/api/pilot/metrics").json()
        assert metrics["family_deletion_failures"] == 0


def test_deletion_requires_exact_confirmation(tmp_path) -> None:
    app = create_app(tmp_path / "guardian.db", tmp_path / "evidence")
    with TestClient(app):
        with pytest.raises(ValueError, match="exactly match"):
            delete_with_confirmation(app.state.store, "family-demo", "wrong-family")
        assert app.state.store.child_exists("child-demo")


def test_deletion_rejects_evidence_path_outside_configured_root(tmp_path) -> None:
    database = tmp_path / "guardian.db"
    evidence_directory = tmp_path / "evidence"
    outside_file = tmp_path / "outside-evidence.txt"
    outside_file.write_text("must remain", encoding="utf-8")
    app = create_app(database, evidence_directory)
    with TestClient(app) as client:
        _, evidence_id = seed_family_scope(client)
        with sqlite3.connect(database) as connection:
            connection.execute(
                "UPDATE incident_evidence SET file_path = ? WHERE id = ?",
                (str(outside_file), evidence_id),
            )

        with pytest.raises(ValueError, match="escapes"):
            app.state.store.delete_family("family-demo")

        assert app.state.store.child_exists("child-demo")
        assert outside_file.read_text(encoding="utf-8") == "must remain"
        with sqlite3.connect(database) as connection:
            assert connection.execute("SELECT COUNT(*) FROM family_deletion_receipts").fetchone()[0] == 0


def test_staging_failure_preserves_family_and_is_operationally_visible(monkeypatch, tmp_path) -> None:
    database = tmp_path / "guardian.db"
    evidence_directory = tmp_path / "evidence"
    app = create_app(database, evidence_directory)
    with TestClient(app) as client:
        _, evidence_id = seed_family_scope(client)
        evidence_path, _ = app.state.store.get_evidence(evidence_id)
        original_replace = Path.replace

        def fail_evidence_move(path: Path, target: Path) -> Path:
            if path == evidence_path:
                raise OSError("simulated staging failure")
            return original_replace(path, target)

        monkeypatch.setattr(Path, "replace", fail_evidence_move)
        with pytest.raises(RuntimeError, match="Unable to stage"):
            app.state.store.delete_family("family-demo")

        assert app.state.store.child_exists("child-demo")
        assert evidence_path.is_file()
        metrics = client.get("/api/pilot/metrics").json()
        assert metrics["family_deletion_failures"] == 1
        with sqlite3.connect(database) as connection:
            status = connection.execute("SELECT status FROM family_deletion_receipts").fetchone()[0]
        assert status == "FAILED_STORAGE_CLEANUP"
