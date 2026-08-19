from datetime import UTC, datetime
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from PIL import Image

import agent.client as client_module
import agent.main as agent_main
from agent.client import GuardianAPIClient, GuardianAPIError
from agent.outbox import PersistentOutbox
from agent.state import AgentStateStore
from api.main import create_app
from guardian_core.config import Environment, GuardianSettings, LogLevel
from guardian_core.models import RiskAssessment
from risk_engine.openai import OpenAIRiskError

PNG_BUFFER = BytesIO()
Image.new("RGB", (8, 8), color="white").save(PNG_BUFFER, format="PNG")
PNG = PNG_BUFFER.getvalue()


def development_settings(tmp_path: Path, environment: Environment = Environment.DEVELOPMENT):
    return GuardianSettings(
        environment=environment,
        database_path=tmp_path / "guardian.db",
        evidence_directory=tmp_path / "evidence",
        api_url="http://testserver",
        log_level=LogLevel.INFO,
        automatic_blocking_enabled=True,
        real_enforcement_enabled=False,
        release_gate_approved=False,
    )


def live_args(tmp_path: Path, **overrides):
    values = {
        "controlled_demo": True,
        "api_url": "http://testserver",
        "child_id": "child-demo",
        "device_id": "device-demo",
        "state_path": tmp_path / "agent-state.json",
        "countdown": 0,
        "openai_timeout": 4,
        "wait_for_unlock": False,
        "poll_interval": 0,
        "real_enforcement": False,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


class FakeObserver:
    def __init__(self, events):
        self.events = events
        self.screenshot_path = None

    def capture_screen(self, destination):
        self.screenshot_path = destination
        destination.write_bytes(PNG)
        self.events.append("capture")
        return destination

    def get_active_application(self):
        self.events.append("active-app")
        return "Guardian Demo Chat"

    def detect_change(self, screenshot_path):
        self.events.append("detect-change")
        return True, "screen-digest"


class FakeClient:
    def __init__(self, events):
        self.events = events
        self.incidents = []
        self.uploads = []
        self.telemetry = []

    def get_policy(self, child_id):
        self.events.append("policy")
        return [
            {
                "category": "DANGEROUS_CONTACT",
                "action": "BLOCK",
                "minimum_risk": "HIGH",
                "minimum_confidence": 0.75,
            }
        ]

    def record_telemetry(self, device_id, payload):
        self.events.append("telemetry")
        self.telemetry.append((device_id, payload))

    def record_heartbeat(self, device_id, payload):
        self.events.append("heartbeat")
        return {"id": device_id, "protection_status": "PROTECTED"}

    def create_incident(self, payload):
        self.events.append("incident")
        self.incidents.append(payload)
        return {"id": "incident-live", "status": "BLOCKED"}

    def upload_png_evidence(self, incident_id, content):
        self.events.append("upload")
        self.uploads.append((incident_id, content))
        return {"id": "evidence-live", "url": "/api/evidence/evidence-live"}


class FakeEnforcer:
    def __init__(self, events):
        self.events = events
        self.blocked = []

    def block(self, application):
        self.events.append("block")
        self.blocked.append(application)


def high_assessment():
    return RiskAssessment(
        risk="HIGH",
        category="DANGEROUS_CONTACT",
        direction="CHILD_AS_TARGET",
        confidence=0.94,
        evidence=["Age, school and photo requested in sequence."],
        explanation="The visible chat progressively requests personal information.",
    )


def safe_assessment():
    return RiskAssessment(
        risk="SAFE",
        category=None,
        direction=None,
        confidence=0.97,
        evidence=[],
        explanation="No supported risk is visible.",
    )


def configure_live_fakes(monkeypatch, tmp_path, assessment):
    events = []
    observer = FakeObserver(events)
    client = FakeClient(events)
    enforcer = FakeEnforcer(events)
    settings = development_settings(tmp_path)
    monkeypatch.setattr(agent_main.GuardianSettings, "from_env", classmethod(lambda cls: settings))
    monkeypatch.setattr(agent_main, "MacOSObserver", lambda: observer)
    monkeypatch.setattr(agent_main, "GuardianAPIClient", lambda api_url: client)
    monkeypatch.setattr(agent_main, "build_enforcer", lambda *args: enforcer)
    monkeypatch.setattr(agent_main, "assess_screenshot", lambda *args, **kwargs: assessment)
    return events, observer, client, enforcer


def incident_payload():
    assessment = high_assessment()
    return {
        "child_id": "child-demo",
        "device_id": "device-demo",
        "application": "Guardian Demo Chat",
        "occurred_at": datetime.now(UTC).isoformat(),
        "assessment": assessment.model_dump(mode="json"),
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
        "deduplication_key": "live-demo-image-evidence",
    }


def test_live_demo_captures_assesses_uploads_then_blocks(monkeypatch, tmp_path, capsys) -> None:
    events, observer, client, enforcer = configure_live_fakes(monkeypatch, tmp_path, high_assessment())

    assert agent_main.run_live_demo(live_args(tmp_path)) == 0

    output = capsys.readouterr().out
    assert "source=OPENAI risk=HIGH category=DANGEROUS_CONTACT confidence=0.94" in output
    assert "incident=incident-live status=BLOCKED" in output
    assert "parent_view=http://testserver/incidents/incident-live" in output
    assert events.index("incident") < events.index("upload") < events.index("block")
    assert enforcer.blocked == ["Guardian Demo Chat"]
    assert client.uploads[0][0] == "incident-live"
    with Image.open(BytesIO(client.uploads[0][1])) as uploaded_image:
        assert uploaded_image.size == (8, 8)
    assert client.incidents[0]["assessment"]["risk"] == "HIGH"
    assert "action" not in client.incidents[0]["assessment"]
    assert observer.screenshot_path is not None
    assert not observer.screenshot_path.exists()


def test_safe_live_assessment_creates_no_incident(monkeypatch, tmp_path, capsys) -> None:
    _, observer, client, enforcer = configure_live_fakes(monkeypatch, tmp_path, safe_assessment())

    assert agent_main.run_live_demo(live_args(tmp_path)) == 0

    output = capsys.readouterr().out
    assert "source=OPENAI risk=SAFE category=None confidence=0.97" in output
    assert "No incident created." in output
    assert client.incidents == []
    assert client.uploads == []
    assert enforcer.blocked == []
    assert not observer.screenshot_path.exists()


def test_remote_failure_returns_nonzero_without_incident_or_block(monkeypatch, tmp_path, capsys) -> None:
    events, observer, client, enforcer = configure_live_fakes(monkeypatch, tmp_path, high_assessment())

    def fail_remote(*args, **kwargs):
        raise OpenAIRiskError("OpenAI request timed out")

    monkeypatch.setattr(agent_main, "assess_screenshot", fail_remote)
    code = agent_main.main(["live-demo", "--controlled-demo", "--countdown", "0"])

    assert code == 1
    assert capsys.readouterr().out.strip().endswith("Guardian agent error: OpenAI request timed out")
    assert client.incidents == []
    assert client.uploads == []
    assert enforcer.blocked == []
    assert "policy" not in events
    assert not observer.screenshot_path.exists()


def test_invalid_assessment_is_rejected_before_policy(monkeypatch, tmp_path) -> None:
    events, observer, client, enforcer = configure_live_fakes(monkeypatch, tmp_path, high_assessment())
    monkeypatch.setattr(
        agent_main,
        "assess_screenshot",
        lambda *args, **kwargs: {
            "risk": "HIGH",
            "category": "DANGEROUS_CONTACT",
            "direction": "CHILD_AS_TARGET",
            "confidence": 0.99,
            "evidence": [],
            "explanation": "invalid because action is classifier-owned",
            "action": "BLOCK",
        },
    )

    with pytest.raises(ValueError, match="action"):
        agent_main.run_live_demo(live_args(tmp_path))

    assert "policy" not in events
    assert client.incidents == []
    assert enforcer.blocked == []
    assert not observer.screenshot_path.exists()


def test_controlled_demo_is_rejected_outside_development(monkeypatch, tmp_path) -> None:
    settings = development_settings(tmp_path, Environment.TEST)
    monkeypatch.setattr(agent_main.GuardianSettings, "from_env", classmethod(lambda cls: settings))
    monkeypatch.setattr(
        agent_main,
        "MacOSObserver",
        lambda: (_ for _ in ()).throw(AssertionError("observer must not start")),
    )

    with pytest.raises(ValueError, match="only in development"):
        agent_main.run_live_demo(live_args(tmp_path))


def test_wait_for_unlock_reuses_existing_polling(monkeypatch, tmp_path) -> None:
    _, observer, client, enforcer = configure_live_fakes(monkeypatch, tmp_path, high_assessment())
    polling = []

    def poll(*args, **kwargs):
        assert not observer.screenshot_path.exists()
        polling.append((args, kwargs))

    monkeypatch.setattr(agent_main, "poll_commands", poll)

    assert agent_main.run_live_demo(live_args(tmp_path, wait_for_unlock=True)) == 0

    assert polling[0][0] == (client, "device-demo", enforcer, 0)
    assert isinstance(polling[0][1]["state_store"], AgentStateStore)


def test_png_client_uses_image_content_type(monkeypatch) -> None:
    captured = {}

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self):
            return b'{"id":"evidence-live","url":"/api/evidence/evidence-live"}'

    def fake_urlopen(request, timeout):
        captured["request"] = request
        captured["timeout"] = timeout
        return Response()

    monkeypatch.setattr(client_module, "urlopen", fake_urlopen)
    result = GuardianAPIClient("http://testserver").upload_png_evidence("incident-live", PNG)

    assert result["id"] == "evidence-live"
    assert captured["request"].get_header("Content-type") == "image/png"
    assert captured["request"].data == PNG
    assert captured["timeout"] == 10


def test_png_evidence_is_accessible_from_existing_route(tmp_path) -> None:
    app = create_app(tmp_path / "guardian.db", tmp_path / "evidence")
    with TestClient(app) as client:
        incident = client.post("/api/incidents", json=incident_payload()).json()
        uploaded = client.post(
            f"/api/incidents/{incident['id']}/evidence",
            content=PNG,
            headers={"Content-Type": "image/png"},
        )
        assert uploaded.status_code == 201
        evidence = client.get(uploaded.json()["url"])

    assert evidence.status_code == 200
    assert evidence.headers["content-type"] == "image/png"
    assert evidence.content == PNG


def test_parser_exposes_the_documented_live_demo_contract() -> None:
    args = agent_main.build_parser().parse_args(["live-demo", "--controlled-demo", "--wait-for-unlock"])

    assert args.handler is agent_main.run_live_demo
    assert args.controlled_demo is True
    assert args.wait_for_unlock is True


def test_observe_command_integrates_real_observer_with_pipeline(monkeypatch, tmp_path) -> None:
    events = []
    client = FakeClient(events)
    enforcer = FakeEnforcer(events)
    settings = development_settings(tmp_path)

    class LoopObserver:
        def capture_if_changed(self, destination):
            Image.new("RGB", (8, 8), color="white").save(destination)
            events.append("capture")
            return destination, "perceptual-hash"

        def get_active_application(self):
            events.append("active-app")
            return "Guardian Demo Chat"

    monkeypatch.setattr(agent_main.GuardianSettings, "from_env", classmethod(lambda cls: settings))
    monkeypatch.setattr(agent_main, "MacOSObserver", lambda **kwargs: LoopObserver())
    monkeypatch.setattr(agent_main, "GuardianAPIClient", lambda api_url: client)
    monkeypatch.setattr(agent_main, "build_enforcer", lambda *args: enforcer)
    monkeypatch.setattr(
        agent_main,
        "assess_screenshot",
        lambda *args, **kwargs: events.append("assessment") or high_assessment(),
    )
    args = agent_main.build_parser().parse_args(["observe", "--max-cycles", "1"])
    args.state_path = tmp_path / "agent-state.json"
    args.runtime_state_path = tmp_path / "runtime-state.json"
    args.outbox_path = tmp_path / "outbox.json"

    assert agent_main.run_observer(args) == 0

    assert events[:4] == ["capture", "active-app", "heartbeat", "assessment"]
    assert client.incidents[0]["decision"]["action"] == "ALERT"
    assert client.uploads[0][0] == "incident-live"
    assert enforcer.blocked == []


def test_observe_command_skips_analysis_for_static_screen(monkeypatch, tmp_path) -> None:
    settings = development_settings(tmp_path)

    class StaticObserver:
        def capture_if_changed(self, destination):
            return None

    monkeypatch.setattr(agent_main.GuardianSettings, "from_env", classmethod(lambda cls: settings))
    monkeypatch.setattr(agent_main, "MacOSObserver", lambda **kwargs: StaticObserver())
    monkeypatch.setattr(agent_main, "GuardianAPIClient", lambda api_url: FakeClient([]))
    monkeypatch.setattr(agent_main, "build_enforcer", lambda *args: FakeEnforcer([]))
    monkeypatch.setattr(
        agent_main,
        "assess_screenshot",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("static screen must be ignored")),
    )
    args = agent_main.build_parser().parse_args(["observe", "--max-cycles", "1"])
    args.runtime_state_path = tmp_path / "runtime-state.json"
    args.outbox_path = tmp_path / "outbox.json"

    assert agent_main.run_observer(args) == 0


def test_observe_command_queues_telemetry_and_incident_when_api_is_offline(monkeypatch, tmp_path) -> None:
    events = []
    settings = development_settings(tmp_path)

    class OfflineClient(FakeClient):
        def record_telemetry(self, device_id, payload):
            raise GuardianAPIError("offline")

        def create_incident(self, payload):
            raise GuardianAPIError("offline")

    class LoopObserver:
        def capture_if_changed(self, destination):
            Image.new("RGB", (8, 8), color="white").save(destination)
            return destination, "offline-hash"

        def get_active_application(self):
            return "Guardian Demo Chat"

    monkeypatch.setattr(agent_main.GuardianSettings, "from_env", classmethod(lambda cls: settings))
    monkeypatch.setattr(agent_main, "MacOSObserver", lambda **kwargs: LoopObserver())
    monkeypatch.setattr(agent_main, "GuardianAPIClient", lambda api_url: OfflineClient(events))
    monkeypatch.setattr(agent_main, "build_enforcer", lambda *args: FakeEnforcer(events))
    monkeypatch.setattr(agent_main, "assess_screenshot", lambda *args, **kwargs: high_assessment())
    args = agent_main.build_parser().parse_args(["observe", "--max-cycles", "1"])
    args.runtime_state_path = tmp_path / "runtime-state.json"
    args.outbox_path = tmp_path / "outbox.json"

    assert agent_main.run_observer(args) == 0

    assert [item.kind for item in PersistentOutbox(args.outbox_path).items()] == [
        "TELEMETRY",
        "INCIDENT",
    ]
