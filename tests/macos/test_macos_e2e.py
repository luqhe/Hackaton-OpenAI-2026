from __future__ import annotations

import hashlib
import os
import platform
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from agent.enforcer import DemoEnforcer
from agent.main import load_fixture
from agent.observer import MacOSObserver
from api.main import create_app
from guardian_core.models import IncidentCreate, PolicyRule
from guardian_core.policy import apply_policy
from risk_engine import assess_risk

PROJECT_ROOT = Path(__file__).resolve().parents[2]

pytestmark = [
    pytest.mark.macos_e2e,
    pytest.mark.skipif(platform.system() != "Darwin", reason="requires macOS"),
    pytest.mark.skipif(
        os.getenv("GUARDIAN_MACOS_E2E") != "1",
        reason="set GUARDIAN_MACOS_E2E=1 on a permissioned test Mac",
    ),
]


def test_real_capture_risk_block_unlock_and_ack(tmp_path) -> None:
    screenshot_path = tmp_path / "real-capture.png"
    observer = MacOSObserver()
    observer.capture_screen(screenshot_path)
    changed, screen_hash = observer.detect_change(screenshot_path)
    assert changed is True

    observation, transcript = load_fixture(PROJECT_ROOT / "fixtures" / "dangerous_contact" / "session.json")
    observation = observation.model_copy(update={"screen_hash": screen_hash})
    assessment = assess_risk(observation)
    enforcer = DemoEnforcer(tmp_path / "blocked-apps.json")
    app = create_app(tmp_path / "guardian.db", tmp_path / "evidence")

    with TestClient(app) as client:
        rules = [
            PolicyRule.model_validate(item) for item in client.get("/api/children/child-demo/policy").json()
        ]
        decision = apply_policy(assessment, rules)
        assert decision.action == "BLOCK"
        enforcer.block(observation.app_name)

        incident = client.post(
            "/api/incidents",
            json=IncidentCreate(
                child_id="child-demo",
                device_id="device-demo",
                application=observation.app_name,
                assessment=assessment,
                decision=decision,
                deduplication_key=hashlib.sha256(transcript.encode()).hexdigest(),
            ).model_dump(mode="json"),
        )
        assert incident.status_code == 201
        incident_id = incident.json()["id"]
        evidence = client.post(
            f"/api/incidents/{incident_id}/evidence",
            content=screenshot_path.read_bytes(),
            headers={"Content-Type": "image/png"},
        )
        assert evidence.status_code == 201
        unlock = client.post(f"/api/incidents/{incident_id}/unlock")
        assert unlock.status_code == 200

        commands = client.get("/api/devices/device-demo/commands").json()
        assert len(commands) == 1
        command = commands[0]
        enforcer.unblock(command["application"])
        acknowledged = client.post(f"/api/devices/device-demo/commands/{command['id']}/ack")
        assert acknowledged.status_code == 200
        assert acknowledged.json()["status"] == "ACKNOWLEDGED"

    assert "Guardian Demo Chat" not in enforcer.blocked_apps
