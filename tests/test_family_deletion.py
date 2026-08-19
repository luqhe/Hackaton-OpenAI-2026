import sqlite3
from datetime import UTC, datetime, timedelta
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
    onboarding_started_at = datetime.now(UTC)
    for index, stage in enumerate(
        (
            "STARTED",
            "PRIVACY_REVIEWED",
            "CONSENT_RECORDED",
            "CHILD_PROFILE_CONFIGURED",
            "DEVICE_PAIRED",
            "PERMISSIONS_GRANTED",
            "FIRST_HEALTHY_HEARTBEAT",
            "SHADOW_READY",
        )
    ):
        response = client.post(
            "/api/pilot/onboarding-events",
            json={
                "child_id": "child-demo",
                "device_id": "device-demo",
                "session_id": "deletion-session-0001",
                "stage": stage,
                "occurred_at": (onboarding_started_at + timedelta(seconds=index)).isoformat(),
                "idempotency_key": f"deletion-onboarding-{index:02d}",
            },
        )
        assert response.status_code == 201
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
        assert receipt.counts.onboarding_events == 8
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


def test_v1_database_migrates_family_id_to_not_null_cascading_foreign_key(tmp_path) -> None:
    database = tmp_path / "legacy.db"
    with sqlite3.connect(database) as connection:
        connection.executescript(
            """
            CREATE TABLE children (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            INSERT INTO children(id, name, created_at)
            VALUES ('child-demo', 'Lucas', '2026-08-19T00:00:00+00:00');
            CREATE TABLE devices (
                id TEXT PRIMARY KEY,
                child_id TEXT NOT NULL REFERENCES children(id),
                name TEXT NOT NULL,
                platform TEXT NOT NULL,
                paired_at TEXT NOT NULL,
                last_seen_at TEXT,
                protection_status TEXT NOT NULL DEFAULT 'PROTECTED'
            );
            INSERT INTO devices(
                id, child_id, name, platform, paired_at, last_seen_at, protection_status
            ) VALUES (
                'device-demo', 'child-demo', 'Legacy Mac', 'macOS',
                '2026-08-19T00:00:00+00:00', NULL, 'PROTECTED'
            );
            PRAGMA user_version = 1;
            """
        )

    app = create_app(database, tmp_path / "evidence")
    with TestClient(app):
        pass

    with sqlite3.connect(database) as connection:
        connection.row_factory = sqlite3.Row
        family_column = next(
            row for row in connection.execute("PRAGMA table_info(children)") if row["name"] == "family_id"
        )
        family_foreign_key = next(
            row
            for row in connection.execute("PRAGMA foreign_key_list(children)")
            if row["from"] == "family_id"
        )
        child = connection.execute("SELECT family_id FROM children WHERE id = 'child-demo'").fetchone()
        device = connection.execute("SELECT child_id FROM devices WHERE id = 'device-demo'").fetchone()
        violations = connection.execute("PRAGMA foreign_key_check").fetchall()

    assert family_column["notnull"] == 1
    assert family_foreign_key["table"] == "families"
    assert family_foreign_key["on_delete"] == "CASCADE"
    assert child["family_id"] == "family-demo"
    assert device["child_id"] == "child-demo"
    assert violations == []


def test_database_and_restore_failures_leave_terminal_resumable_receipt(monkeypatch, tmp_path) -> None:
    database = tmp_path / "guardian.db"
    evidence_directory = tmp_path / "evidence"
    app = create_app(database, evidence_directory)
    with TestClient(app) as client:
        _, evidence_id = seed_family_scope(client)
        evidence_path, _ = app.state.store.get_evidence(evidence_id)
        original_replace = Path.replace

        def fail_verification(*_args, **_kwargs) -> None:
            raise RuntimeError("simulated database verification failure")

        def fail_restore(path: Path, target: Path) -> Path:
            if ".deletion-staging" in path.parts:
                raise OSError("simulated restore failure")
            return original_replace(path, target)

        monkeypatch.setattr(app.state.store, "_verify_family_scope_removed", fail_verification)
        monkeypatch.setattr(Path, "replace", fail_restore)
        with pytest.raises(RuntimeError, match="rollback was incomplete") as error:
            app.state.store.delete_family("family-demo")

        assert isinstance(error.value.__cause__, RuntimeError)
        assert app.state.store.child_exists("child-demo")
        assert not evidence_path.exists()
        with sqlite3.connect(database) as connection:
            receipt_id, status, staging = connection.execute(
                "SELECT id, status, staging_directory FROM family_deletion_receipts"
            ).fetchone()
        assert status == "FAILED_DATABASE"
        assert staging is not None
        assert Path(staging).is_dir()

        monkeypatch.setattr(Path, "replace", original_replace)
        receipt = app.state.store.resume_family_deletion(receipt_id)
        assert receipt.status == "FAILED_DATABASE"
        assert evidence_path.is_file()
        assert not Path(staging).exists()


def test_storage_cleanup_failure_can_resume_to_completion(monkeypatch, tmp_path) -> None:
    database = tmp_path / "guardian.db"
    evidence_directory = tmp_path / "evidence"
    app = create_app(database, evidence_directory)
    with TestClient(app) as client:
        seed_family_scope(client)
        original_unlink = Path.unlink

        def fail_staged_unlink(path: Path, *args, **kwargs) -> None:
            if ".deletion-staging" in path.parts:
                raise OSError("simulated final cleanup failure")
            original_unlink(path, *args, **kwargs)

        monkeypatch.setattr(Path, "unlink", fail_staged_unlink)
        with pytest.raises(RuntimeError, match="cleanup is incomplete"):
            app.state.store.delete_family("family-demo")

        assert not app.state.store.child_exists("child-demo")
        with sqlite3.connect(database) as connection:
            receipt_id, status, staging = connection.execute(
                "SELECT id, status, staging_directory FROM family_deletion_receipts"
            ).fetchone()
        assert status == "FAILED_STORAGE_CLEANUP"
        assert staging is not None

        monkeypatch.setattr(Path, "unlink", original_unlink)
        receipt = app.state.store.resume_family_deletion(receipt_id)
        assert receipt.status == "COMPLETED"
        assert receipt.completed_at is not None
        assert not Path(staging).exists()
