import json

from agent.state import AgentRuntimeState, AgentStateStore


def test_agent_runtime_state_survives_restart(tmp_path) -> None:
    store = AgentStateStore(tmp_path / "runtime-state.json")
    state = AgentRuntimeState().update(
        session_id="minecraft-session",
        last_screen_hash="abc123",
        last_command_id=42,
    )

    store.save(state)
    restored = AgentStateStore(store.path).load()

    assert restored.session_id == "minecraft-session"
    assert restored.last_screen_hash == "abc123"
    assert restored.last_command_id == 42
    assert restored.updated_at is not None


def test_agent_state_write_is_atomic_and_leaves_no_temporary_file(tmp_path) -> None:
    store = AgentStateStore(tmp_path / "runtime-state.json")

    store.save(AgentRuntimeState().update(last_command_id=1))
    store.save(AgentRuntimeState().update(last_command_id=2))

    assert json.loads(store.path.read_text(encoding="utf-8"))["last_command_id"] == 2
    assert list(tmp_path.glob("*.tmp")) == []


def test_corrupt_or_future_state_fails_closed_to_empty_cursor(tmp_path) -> None:
    store = AgentStateStore(tmp_path / "runtime-state.json")
    store.path.write_text('{"schema_version":999}', encoding="utf-8")

    assert store.load() == AgentRuntimeState()

    store.path.write_text("not-json", encoding="utf-8")
    assert store.load() == AgentRuntimeState()
