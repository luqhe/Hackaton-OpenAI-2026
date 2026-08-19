from __future__ import annotations

import json
import os
import tempfile
from dataclasses import asdict, dataclass, replace
from datetime import UTC, datetime
from pathlib import Path


@dataclass(frozen=True, slots=True)
class AgentRuntimeState:
    schema_version: int = 1
    session_id: str = "interactive"
    last_screen_hash: str | None = None
    last_command_id: int = 0
    command_scope: str | None = None
    updated_at: str | None = None

    def update(self, **changes: object) -> AgentRuntimeState:
        return replace(self, updated_at=datetime.now(UTC).isoformat(), **changes)


class AgentStateStore:
    """Atomically persists non-sensitive runtime cursors for crash recovery."""

    def __init__(self, path: Path):
        self.path = path

    def load(self) -> AgentRuntimeState:
        if not self.path.is_file():
            return AgentRuntimeState()
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
            state = AgentRuntimeState(**payload)
            if state.schema_version != 1:
                raise ValueError("unsupported agent state schema")
            if state.last_command_id < 0:
                raise ValueError("last_command_id cannot be negative")
            return state
        except (OSError, TypeError, ValueError, json.JSONDecodeError):
            return AgentRuntimeState()

    def save(self, state: AgentRuntimeState) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        handle = tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            prefix=f".{self.path.name}.",
            suffix=".tmp",
            dir=self.path.parent,
            delete=False,
        )
        temporary_path = Path(handle.name)
        try:
            with handle:
                json.dump(asdict(state), handle, sort_keys=True, separators=(",", ":"))
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary_path, self.path)
        finally:
            temporary_path.unlink(missing_ok=True)
