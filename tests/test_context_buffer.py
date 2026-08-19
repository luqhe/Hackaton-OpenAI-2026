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
