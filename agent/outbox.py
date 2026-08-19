from __future__ import annotations

import json
import os
import tempfile
from collections.abc import Callable
from dataclasses import asdict, dataclass, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal
from uuid import uuid4

from guardian_core.pilot import PilotTechnicalTelemetry

OutboxKind = Literal["INCIDENT", "TELEMETRY", "PILOT_TELEMETRY"]


@dataclass(frozen=True, slots=True)
class OutboxItem:
    id: str
    kind: OutboxKind
    device_id: str
    payload: dict[str, Any]
    created_at: str
    attempts: int = 0


class PersistentOutbox:
    """Small atomic FIFO for operations that must survive API outages."""

    def __init__(self, path: Path, *, maximum_items: int = 1000):
        if maximum_items <= 0:
            raise ValueError("maximum_items must be positive")
        self.path = path
        self.maximum_items = maximum_items

    def items(self) -> tuple[OutboxItem, ...]:
        if not self.path.is_file():
            return ()
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
            return tuple(OutboxItem(**item) for item in payload)
        except (OSError, TypeError, ValueError, json.JSONDecodeError):
            return ()

    def enqueue(self, kind: OutboxKind, device_id: str, payload: dict[str, Any]) -> OutboxItem:
        if kind == "PILOT_TELEMETRY":
            payload = PilotTechnicalTelemetry.model_validate(payload).model_dump(
                mode="json", exclude_none=True
            )
        queued = list(self.items())
        if len(queued) >= self.maximum_items:
            raise RuntimeError("offline outbox capacity reached")
        item = OutboxItem(
            id=str(uuid4()),
            kind=kind,
            device_id=device_id,
            payload=payload,
            created_at=datetime.now(UTC).isoformat(),
        )
        queued.append(item)
        self._save(queued)
        return item

    def flush(self, deliver: Callable[[OutboxItem], bool], *, limit: int = 50) -> int:
        if limit <= 0:
            raise ValueError("limit must be positive")
        queued = list(self.items())
        delivered = 0
        while queued and delivered < limit:
            item = queued[0]
            if not deliver(item):
                queued[0] = replace(item, attempts=item.attempts + 1)
                break
            queued.pop(0)
            delivered += 1
        self._save(queued)
        return delivered

    def _save(self, items: list[OutboxItem]) -> None:
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
                json.dump([asdict(item) for item in items], handle, separators=(",", ":"))
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary_path, self.path)
        finally:
            temporary_path.unlink(missing_ok=True)
