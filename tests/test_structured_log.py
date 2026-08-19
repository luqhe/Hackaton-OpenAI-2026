import json
from io import StringIO

from agent.structured_log import REDACTED, StructuredAgentLogger, sanitize_log_value


def test_structured_log_redacts_sensitive_fields_and_secret_values() -> None:
    stream = StringIO()
    logger = StructuredAgentLogger(stream)

    logger.event(
        "analysis_failed",
        api_key="sk-super-secret-value",
        authorization="Bearer private-token",
        visible_text="personal chat",
        screenshot_path="/tmp/child.png",
        detail="request using sk-another-secret-value failed",
        category="DANGEROUS_CONTACT",
    )
    payload = json.loads(stream.getvalue())

    assert payload["api_key"] == REDACTED
    assert payload["authorization"] == REDACTED
    assert payload["visible_text"] == REDACTED
    assert payload["screenshot_path"] == REDACTED
    assert "sk-" not in payload["detail"]
    assert payload["category"] == "DANGEROUS_CONTACT"


def test_structured_log_sanitizes_nested_collections() -> None:
    sanitized = sanitize_log_value(
        {
            "device": {"id": "device-demo", "transcript": "private"},
            "headers": ["Bearer hidden-token"],
        }
    )

    assert sanitized["device"]["id"] == "device-demo"
    assert sanitized["device"]["transcript"] == REDACTED
    assert sanitized["headers"] == [REDACTED]
