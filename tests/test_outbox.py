from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from agent.main import flush_offline_outbox
from agent.outbox import PersistentOutbox


def test_outbox_survives_restart_and_flushes_fifo(tmp_path) -> None:
    path = tmp_path / "outbox.json"
    outbox = PersistentOutbox(path)
    first = outbox.enqueue("TELEMETRY", "device-demo", {"sequence": 1})
    second = outbox.enqueue("INCIDENT", "device-demo", {"sequence": 2})
    delivered = []

    restored = PersistentOutbox(path)
    count = restored.flush(lambda item: delivered.append(item) or True)

    assert count == 2
    assert [item.id for item in delivered] == [first.id, second.id]
    assert restored.items() == ()


def test_outbox_stops_at_first_failed_delivery_and_counts_attempt(tmp_path) -> None:
    outbox = PersistentOutbox(tmp_path / "outbox.json")
    first = outbox.enqueue("TELEMETRY", "device-demo", {"sequence": 1})
    outbox.enqueue("INCIDENT", "device-demo", {"sequence": 2})

    assert outbox.flush(lambda item: False) == 0

    queued = outbox.items()
    assert queued[0].id == first.id
    assert queued[0].attempts == 1
    assert len(queued) == 2


def test_outbox_has_bounded_capacity(tmp_path) -> None:
    outbox = PersistentOutbox(tmp_path / "outbox.json", maximum_items=1)
    outbox.enqueue("TELEMETRY", "device-demo", {"sequence": 1})

    try:
        outbox.enqueue("TELEMETRY", "device-demo", {"sequence": 2})
    except RuntimeError as error:
        assert "capacity" in str(error)
    else:
        raise AssertionError("bounded outbox accepted too many items")


def test_signed_flush_sanitizes_identity_for_matching_credential(tmp_path) -> None:
    outbox = PersistentOutbox(tmp_path / "outbox.json")
    telemetry = outbox.enqueue(
        "TELEMETRY",
        "legacy-device",
        {"child_id": "legacy-child", "screen_changes": 1},
        credential_id="cred-current",
    )
    outbox.enqueue(
        "INCIDENT",
        "legacy-device",
        {
            "child_id": "legacy-child",
            "device_id": "legacy-device",
            "application": "Browser",
        },
        credential_id="cred-current",
    )

    class SignedClient:
        def __init__(self):
            self.credential = SimpleNamespace(
                device_id="legacy-device",
                credential_id="cred-current",
            )
            self.telemetry = []
            self.incidents = []

        def record_device_telemetry(self, payload):
            self.telemetry.append(payload)

        def create_device_incident(self, payload):
            self.incidents.append(payload)

    client = SignedClient()

    assert flush_offline_outbox(outbox, client) == 2
    assert client.telemetry == [{"screen_changes": 1, "observed_at": telemetry.created_at}]
    assert client.incidents == [{"application": "Browser"}]


def test_signed_flush_retains_item_owned_by_another_device(tmp_path) -> None:
    outbox = PersistentOutbox(tmp_path / "outbox.json")
    queued = outbox.enqueue(
        "TELEMETRY",
        "device-a",
        {"screen_changes": 1},
        credential_id="cred-a",
    )

    class SignedClient:
        credential = SimpleNamespace(device_id="device-a", credential_id="cred-b")

        def __init__(self):
            self.calls = []

        def record_device_telemetry(self, payload):
            self.calls.append(payload)

    client = SignedClient()

    assert flush_offline_outbox(outbox, client) == 0
    assert client.calls == []
    assert outbox.items()[0].id == queued.id


def test_signed_flush_retains_legacy_item_without_credential_binding(tmp_path) -> None:
    outbox = PersistentOutbox(tmp_path / "outbox.json")
    queued = outbox.enqueue("TELEMETRY", "device-a", {"screen_changes": 1})

    class SignedClient:
        credential = SimpleNamespace(device_id="device-a", credential_id="cred-a")

        def record_device_telemetry(self, payload):
            raise AssertionError("unbound legacy item must not be delivered")

    assert flush_offline_outbox(outbox, SignedClient()) == 0
    assert outbox.items()[0].id == queued.id


def test_pilot_telemetry_outbox_rejects_content_fields(tmp_path) -> None:
    outbox = PersistentOutbox(tmp_path / "outbox.json")

    with pytest.raises(ValidationError):
        outbox.enqueue(
            "PILOT_TELEMETRY",
            "device-demo",
            {"agent_version": "0.1.0", "app_name": "Private Chat"},
        )

    item = outbox.enqueue(
        "PILOT_TELEMETRY",
        "device-demo",
        {"agent_version": "0.1.0", "permission_state": "GRANTED"},
    )
    assert item.payload == {"agent_version": "0.1.0", "permission_state": "GRANTED"}


def test_persisted_pilot_telemetry_is_revalidated_before_delivery(tmp_path) -> None:
    path = tmp_path / "outbox.json"
    path.write_text(
        '[{"id":"1","kind":"PILOT_TELEMETRY","device_id":"device-demo",'
        '"payload":{"agent_version":"0.1.0","visible_text":"private"},'
        '"created_at":"2026-08-20T00:00:00+00:00","attempts":0}]',
        encoding="utf-8",
    )

    assert PersistentOutbox(path).items() == ()
