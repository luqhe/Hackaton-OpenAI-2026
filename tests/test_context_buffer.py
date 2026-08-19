from datetime import UTC, datetime, timedelta

import pytest

from agent.context import ContextKey, ObservationContextBuffer
from guardian_core.models import Observation


def observation(application: str, text: str) -> Observation:
    return Observation(app_name=application, visible_text=text)


def test_context_is_isolated_by_application() -> None:
    buffer = ObservationContextBuffer()
    minecraft = buffer.add(observation("Minecraft", "safe build"), session_id="game-1")
    safari = buffer.add(observation("Safari", "biology class"), session_id="browser-1")

    assert [item.visible_text for item in buffer.observations(minecraft)] == ["safe build"]
    assert [item.visible_text for item in buffer.observations(safari)] == ["biology class"]


def test_context_is_isolated_between_sessions_of_same_application() -> None:
    buffer = ObservationContextBuffer()
    first = buffer.add(observation("Minecraft", "first server"), session_id="server-a")
    second = buffer.add(observation("Minecraft", "second server"), session_id="server-b")

    assert first != second
    assert buffer.observations(first)[0].visible_text == "first server"
    assert buffer.observations(second)[0].visible_text == "second server"


def test_context_can_be_cleared_per_session_without_affecting_others() -> None:
    buffer = ObservationContextBuffer()
    first = buffer.add(observation("Minecraft", "first"), session_id="one")
    second = buffer.add(observation("Minecraft", "second"), session_id="two")

    buffer.clear(first)

    assert buffer.observations(first) == ()
    assert buffer.observations(second)[0].visible_text == "second"
    assert tuple(buffer.sessions()) == (ContextKey("Minecraft", "two"),)


def test_context_keeps_only_configured_observation_count() -> None:
    buffer = ObservationContextBuffer(max_observations=5)
    key = None
    for index in range(7):
        key = buffer.add(observation("Minecraft", f"message-{index}"))

    assert key is not None
    assert [item.visible_text for item in buffer.observations(key)] == [
        "message-2",
        "message-3",
        "message-4",
        "message-5",
        "message-6",
    ]


def test_context_discards_observations_older_than_two_minutes() -> None:
    buffer = ObservationContextBuffer(max_age_seconds=120)
    started_at = datetime(2026, 8, 19, 12, tzinfo=UTC)
    old = Observation(app_name="Minecraft", visible_text="old", timestamp=started_at)
    current = Observation(
        app_name="Minecraft",
        visible_text="current",
        timestamp=started_at + timedelta(seconds=121),
    )
    key = buffer.add(old)
    buffer.add(current)

    assert [item.visible_text for item in buffer.observations(key)] == ["current"]


@pytest.mark.parametrize(
    "values",
    [
        {"max_observations": 4},
        {"max_observations": 11},
        {"max_age_seconds": 0},
        {"max_age_seconds": 121},
    ],
)
def test_context_rejects_limits_outside_privacy_budget(values) -> None:
    with pytest.raises(ValueError):
        ObservationContextBuffer(**values)
