from agent.enforcer import DemoEnforcer
from agent.main import poll_commands
from agent.state import AgentRuntimeState, AgentStateStore


class CommandClient:
    def __init__(self, commands, command_scope="api-a/device-a"):
        self.commands = commands
        self.command_scope = command_scope
        self.after_ids = []
        self.acknowledged = []

    def pending_device_commands(self, after_id, wait_seconds):
        self.after_ids.append(after_id)
        return [command for command in self.commands if command["id"] > after_id]

    def acknowledge_device_command(self, command_id, *, result, error_code=None):
        assert result == "EXECUTED"
        assert error_code is None
        self.acknowledged.append(command_id)
        self.commands = [command for command in self.commands if command["id"] != command_id]


def test_unlock_cursor_survives_restart_and_prevents_replay(tmp_path) -> None:
    state_store = AgentStateStore(tmp_path / "runtime-state.json")
    state_path = tmp_path / "blocked.json"
    enforcer = DemoEnforcer(state_path)
    enforcer.block("Guardian Demo Chat")
    client = CommandClient(
        [
            {
                "id": 7,
                "type": "UNLOCK_APPLICATION",
                "application": "Guardian Demo Chat",
                "protocol_version": "1.0",
                "expires_at": "2099-08-19T18:00:00+00:00",
            }
        ]
    )

    poll_commands(client, enforcer, 0, once=True, state_store=state_store)
    restarted_enforcer = DemoEnforcer(state_path)
    restarted_client = CommandClient([])
    poll_commands(
        restarted_client,
        restarted_enforcer,
        0,
        once=True,
        state_store=AgentStateStore(state_store.path),
    )

    assert client.acknowledged == [7]
    assert "Guardian Demo Chat" not in restarted_enforcer.blocked_apps
    assert restarted_client.after_ids == [7]


def test_unlock_cursor_resets_when_authenticated_device_or_backend_changes(tmp_path) -> None:
    state_store = AgentStateStore(tmp_path / "runtime-state.json")
    state_store.save(
        AgentRuntimeState().update(
            last_command_id=42,
            command_scope="api-a/device-a",
        )
    )
    client = CommandClient([], command_scope="api-b/device-b")

    poll_commands(
        client,
        DemoEnforcer(tmp_path / "blocked.json"),
        0,
        once=True,
        state_store=state_store,
    )

    assert client.after_ids == [0]
    assert state_store.load().command_scope == "api-b/device-b"
