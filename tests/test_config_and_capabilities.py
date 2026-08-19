import sqlite3

import pytest
from fastapi.testclient import TestClient

from api.main import create_app
from guardian_core.config import Environment, GuardianSettings
from guardian_core.version import API_VERSION, SCHEMA_VERSION


def environment(overrides: dict[str, str] | None = None) -> dict[str, str]:
    values = {
        "GUARDIAN_ENVIRONMENT": "test",
        "GUARDIAN_API_URL": "http://testserver",
        "GUARDIAN_DB_PATH": ".test-runtime/config.db",
        "GUARDIAN_EVIDENCE_DIR": ".test-runtime/evidence",
        "GUARDIAN_AUTOMATIC_BLOCKING_ENABLED": "false",
        "GUARDIAN_REAL_ENFORCEMENT_ENABLED": "false",
        "GUARDIAN_RELEASE_GATE_APPROVED": "false",
    }
    values.update(overrides or {})
    return values


def test_settings_are_typed_and_environment_specific() -> None:
    settings = GuardianSettings.from_env(environment())
    assert settings.environment == Environment.TEST
    assert settings.automatic_blocking_enabled is False
    assert settings.api_url == "http://testserver"


def test_nonlocal_automatic_blocking_requires_release_gate() -> None:
    with pytest.raises(ValueError, match="release gate"):
        GuardianSettings.from_env(
            environment(
                {
                    "GUARDIAN_ENVIRONMENT": "production",
                    "GUARDIAN_AUTOMATIC_BLOCKING_ENABLED": "true",
                }
            )
        )


def test_capabilities_report_only_implemented_features(tmp_path) -> None:
    settings = GuardianSettings.from_env(environment())
    app = create_app(tmp_path / "guardian.db", tmp_path / "evidence", settings=settings)
    with TestClient(app) as client:
        response = client.get("/api/capabilities")
        assert response.status_code == 200
        assert response.headers["X-Guardian-API-Version"] == API_VERSION
        capabilities = response.json()
        assert capabilities["fixture_analysis"] is True
        assert capabilities["real_screen_observation"] is False
        assert capabilities["local_ocr"] is False
        assert capabilities["system_audio"] is False
        assert capabilities["microphone"] is False
        assert capabilities["camera"] is False
        assert capabilities["production_ready"] is False

        health = client.get("/api/health").json()
        assert health["environment"] == "test"
        assert health["api_version"] == API_VERSION


def test_enforcement_configuration_does_not_claim_an_active_agent(tmp_path) -> None:
    configured = GuardianSettings.from_env(environment({"GUARDIAN_REAL_ENFORCEMENT_ENABLED": "true"}))
    app = create_app(tmp_path / "guardian.db", tmp_path / "evidence", settings=configured)
    with TestClient(app) as client:
        capabilities = client.get("/api/capabilities").json()
    assert capabilities["real_macos_enforcement"] is False
    assert any("authorization gate" in note for note in capabilities["notes"])


def test_storage_records_schema_version(tmp_path) -> None:
    settings = GuardianSettings.from_env(environment())
    database = tmp_path / "guardian.db"
    app = create_app(database, tmp_path / "evidence", settings=settings)
    with TestClient(app):
        pass
    with sqlite3.connect(database) as connection:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == SCHEMA_VERSION
