from __future__ import annotations

import json
import re
import sys
from datetime import UTC, datetime
from typing import Any, TextIO

REDACTED = "[REDACTED]"
SENSITIVE_FIELD_PARTS = (
    "api_key",
    "authorization",
    "content",
    "evidence",
    "image",
    "message",
    "screenshot",
    "secret",
    "text",
    "token",
    "transcript",
)
SECRET_PATTERNS = (
    re.compile(r"\bsk-[A-Za-z0-9_-]{8,}\b"),
    re.compile(r"\bBearer\s+[A-Za-z0-9._~-]+", re.IGNORECASE),
)


def sanitize_log_value(value: Any, *, field_name: str = "") -> Any:
    normalized_name = field_name.casefold()
    if any(part in normalized_name for part in SENSITIVE_FIELD_PARTS):
        return REDACTED
    if isinstance(value, dict):
        return {str(key): sanitize_log_value(item, field_name=str(key)) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [sanitize_log_value(item) for item in value]
    if isinstance(value, str):
        sanitized = value
        for pattern in SECRET_PATTERNS:
            sanitized = pattern.sub(REDACTED, sanitized)
        return sanitized
    if value is None or isinstance(value, (bool, int, float)):
        return value
    return str(value)


class StructuredAgentLogger:
    def __init__(self, stream: TextIO | None = None):
        self.stream = stream or sys.stderr

    def event(self, event: str, *, level: str = "INFO", **fields: Any) -> None:
        payload = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": level,
            "event": event,
            **sanitize_log_value(fields),
        }
        self.stream.write(json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n")
        self.stream.flush()
