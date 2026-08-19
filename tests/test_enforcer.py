import json

import pytest

from agent.enforcer import DemoEnforcer


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
