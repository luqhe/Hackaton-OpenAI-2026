from scripts.validate_pilot_readiness import validate_protocol


def test_pilot_protocol_is_safe_and_complete() -> None:
    assert validate_protocol() == []
