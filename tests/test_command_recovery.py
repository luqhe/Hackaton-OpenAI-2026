from agent.enforcer import DemoEnforcer
from agent.main import poll_commands
from agent.state import AgentStateStore


class CommandClient:
    def __init__(self, commands):
        self.commands = commands
        self.after_ids = []
        self.acknowledged = []

    def pending_commands(self, device_id, after_id):
        self.after_ids.append(after_id)
        return [command for command in self.commands if command["id"] > after_id]

    def acknowledge_command(self, device_id, command_id):
        self.acknowledged.append(command_id)
        self.commands = [command for command in self.commands if command["id"] != command_id]


def test_unlock_cursor_survives_restart_and_prevents_replay(tmp_path) -> None:
    state_store = AgentStateStore(tmp_path / "runtime-state.json")
    state_path = tmp_path / "blocked.json"
    enforcer = DemoEnforcer(state_path)
    enforcer.block("Guardian Demo Chat")
    client = CommandClient([{"id": 7, "type": "UNLOCK_APPLICATION", "application": "Guardian Demo Chat"}])

    poll_commands(client, "device-demo", enforcer, 0, once=True, state_store=state_store)
    restarted_enforcer = DemoEnforcer(state_path)
    restarted_client = CommandClient([])
    poll_commands(
        restarted_client,
        "device-demo",
        restarted_enforcer,
        0,
        once=True,
        state_store=AgentStateStore(state_store.path),
    )

    assert client.acknowledged == [7]
    assert "Guardian Demo Chat" not in restarted_enforcer.blocked_apps
    assert restarted_client.after_ids == [7]
