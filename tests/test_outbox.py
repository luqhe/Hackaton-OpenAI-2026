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
