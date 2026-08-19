from pathlib import Path
from urllib.error import URLError

import pytest

import agent.client as client_module
import agent.main as agent_main
from agent.client import GuardianAPIClient, GuardianAPIError
from agent.observer import ObserverPermissionError
from guardian_core.config import Environment, GuardianSettings, LogLevel
from guardian_core.models import RiskAssessment


def settings(tmp_path: Path) -> GuardianSettings:
    return GuardianSettings(
        environment=Environment.DEVELOPMENT,
        database_path=tmp_path / "guardian.db",
        evidence_directory=tmp_path / "evidence",
        api_url="http://testserver",
        log_level=LogLevel.INFO,
        automatic_blocking_enabled=True,
        real_enforcement_enabled=False,
        release_gate_approved=False,
    )


def observe_arguments(tmp_path: Path) -> list[str]:
    return [
        "observe",
        "--max-cycles",
        "1",
        "--state-path",
        str(tmp_path / "blocked.json"),
        "--runtime-state-path",
        str(tmp_path / "runtime.json"),
        "--outbox-path",
        str(tmp_path / "outbox.json"),
    ]


def test_network_loss_is_reported_as_guardian_api_error(monkeypatch) -> None:
    monkeypatch.setattr(
        client_module,
        "urlopen",
        lambda *args, **kwargs: (_ for _ in ()).throw(URLError("network down")),
    )

    with pytest.raises(GuardianAPIError, match="network down"):
        GuardianAPIClient("http://testserver").get_policy("child-demo")


def test_revoked_permission_stops_observer_without_blocking(monkeypatch, tmp_path) -> None:
    blocked = []

    class RevokedObserver:
        def capture_if_changed(self, destination):
            raise ObserverPermissionError("Screen Recording permission was revoked")

    class Enforcer:
        def block(self, application):
            blocked.append(application)

    monkeypatch.setattr(
        agent_main.GuardianSettings,
        "from_env",
        classmethod(lambda cls: settings(tmp_path)),
    )
    monkeypatch.setattr(agent_main, "MacOSObserver", lambda **kwargs: RevokedObserver())
    monkeypatch.setattr(agent_main, "build_authenticated_client", lambda api_url: object())
    monkeypatch.setattr(agent_main, "build_enforcer", lambda *args: Enforcer())
    monkeypatch.setattr(agent_main, "flush_offline_outbox", lambda *args: 0)

    assert agent_main.main(observe_arguments(tmp_path)) == 1
    assert blocked == []


def test_backend_policy_failure_is_fail_open(monkeypatch, tmp_path) -> None:
    blocked = []

    class Observer:
        def capture_if_changed(self, destination):
            destination.write_bytes(b"unused")
            return destination, "hash"

        def get_active_application(self):
            return "Guardian Demo Chat"

    class OfflineClient:
        def record_device_heartbeat(self, payload):
            return None

        def get_device_policy(self):
            raise GuardianAPIError("backend unavailable")

    class Enforcer:
        def block(self, application):
            blocked.append(application)

    monkeypatch.setattr(
        agent_main.GuardianSettings,
        "from_env",
        classmethod(lambda cls: settings(tmp_path)),
    )
    monkeypatch.setattr(agent_main, "MacOSObserver", lambda **kwargs: Observer())
    monkeypatch.setattr(agent_main, "build_authenticated_client", lambda api_url: OfflineClient())
    monkeypatch.setattr(agent_main, "build_enforcer", lambda *args: Enforcer())
    monkeypatch.setattr(agent_main, "flush_offline_outbox", lambda *args: 0)
    monkeypatch.setattr(
        agent_main,
        "assess_screenshot",
        lambda *args, **kwargs: RiskAssessment(
            risk="HIGH",
            category="DANGEROUS_CONTACT",
            direction="CHILD_AS_TARGET",
            confidence=0.99,
            evidence=[],
            explanation="controlled test assessment",
        ),
    )

    assert agent_main.main(observe_arguments(tmp_path)) == 1
    assert blocked == []
