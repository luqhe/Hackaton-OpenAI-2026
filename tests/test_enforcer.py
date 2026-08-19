import json
from types import SimpleNamespace

import pytest

import agent.enforcer as enforcer_module
from agent.enforcer import DemoEnforcer, MacOSEnforcer


def test_demo_enforcer_persists_block_state(tmp_path) -> None:
    state_path = tmp_path / "state.json"
    enforcer = DemoEnforcer(state_path)
    enforcer.block("Guardian Demo Chat")
    assert json.loads(state_path.read_text())["blocked_apps"] == ["Guardian Demo Chat"]
    reloaded = DemoEnforcer(state_path)
    assert "Guardian Demo Chat" in reloaded.blocked_apps
    reloaded.unblock("Guardian Demo Chat")
    assert json.loads(state_path.read_text())["blocked_apps"] == []


def test_demo_enforcer_refuses_essential_application(tmp_path) -> None:
    enforcer = DemoEnforcer(tmp_path / "state.json")
    with pytest.raises(ValueError):
        enforcer.block("Finder")


@pytest.mark.parametrize(
    "application",
    [
        "finder",
        "/System/Library/CoreServices/Finder.app",
        "WINDOWSERVER",
        "SystemUIServer.app",
        "guardian-capture-helper",
    ],
)
def test_protected_application_matching_is_normalized(tmp_path, application) -> None:
    enforcer = DemoEnforcer(tmp_path / "state.json")

    with pytest.raises(ValueError, match="protected application"):
        enforcer.block(application)


def test_protected_application_is_removed_from_restored_state(tmp_path) -> None:
    state_path = tmp_path / "state.json"
    state_path.write_text(
        json.dumps({"blocked_apps": ["Finder.app", "Guardian Demo Chat"]}),
        encoding="utf-8",
    )

    enforcer = DemoEnforcer(state_path)

    assert enforcer.blocked_apps == {"Guardian Demo Chat"}


def test_macos_enforcer_reapplies_quit_when_blocked_app_reopens(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(enforcer_module.platform, "system", lambda: "Darwin")
    running_states = iter(["true\n", "true\n"])
    quit_calls = []

    def fake_run(command, **kwargs):
        script = command[-1]
        if "exists application process" in script:
            return SimpleNamespace(returncode=0, stdout=next(running_states))
        quit_calls.append(script)
        return SimpleNamespace(returncode=0, stdout="")

    monkeypatch.setattr(enforcer_module.subprocess, "run", fake_run)
    enforcer = MacOSEnforcer(tmp_path / "state.json", {"Guardian Demo Chat"})

    enforcer.block("Guardian Demo Chat")
    enforcer.enforce()

    assert quit_calls == [
        'tell application "Guardian Demo Chat" to quit',
        'tell application "Guardian Demo Chat" to quit',
    ]


def test_macos_enforcer_does_not_activate_closed_application(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(enforcer_module.platform, "system", lambda: "Darwin")
    scripts = []

    def fake_run(command, **kwargs):
        scripts.append(command[-1])
        return SimpleNamespace(returncode=0, stdout="false\n")

    monkeypatch.setattr(enforcer_module.subprocess, "run", fake_run)
    enforcer = MacOSEnforcer(tmp_path / "state.json", {"Guardian Demo Chat"})

    enforcer.block("Guardian Demo Chat")
    enforcer.enforce()

    assert len(scripts) == 2
    assert all("exists application process" in script for script in scripts)
