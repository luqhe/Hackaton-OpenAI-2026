from __future__ import annotations

import hashlib
import json
from datetime import datetime
from enum import StrEnum
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from guardian_core.pilot import PilotMode, PilotRolloutConfig, load_pilot_rollout


class PilotChangeAction(StrEnum):
    ACTIVATE = "ACTIVATE"
    ROLLBACK = "ROLLBACK"


class PilotConfigChange(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: str = "guardian.pilot-config-change.v1"
    action: PilotChangeAction
    previous_digest: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    active_digest: str = Field(pattern=r"^[a-f0-9]{64}$")
    actor_subject_digest: str = Field(pattern=r"^[a-f0-9]{64}$")
    change_reference: str = Field(min_length=1, max_length=120)
    changed_at: datetime


def _canonical_payload(config: PilotRolloutConfig) -> dict[str, object]:
    payload = config.model_dump(mode="json")
    payload["cohort_ids"] = sorted(payload["cohort_ids"])
    payload["technical_telemetry_fields"] = sorted(payload["technical_telemetry_fields"])
    for collection_name in ("alert_approvals", "block_approvals"):
        approvals = payload[collection_name]
        for approval in approvals:
            approval["cohort_ids"] = sorted(approval["cohort_ids"])
        payload[collection_name] = sorted(approvals, key=lambda item: item["approval_id"])
    payload["kill_switches"] = sorted(payload["kill_switches"], key=lambda item: item["switch_id"])
    return payload


def pilot_config_json(config: PilotRolloutConfig) -> str:
    return json.dumps(_canonical_payload(config), indent=2, sort_keys=True) + "\n"


def pilot_config_digest(config: PilotRolloutConfig) -> str:
    canonical = json.dumps(_canonical_payload(config), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


class PilotConfigStore:
    """Atomic active config plus content-addressed snapshots and append-only change audit."""

    def __init__(self, state_directory: Path) -> None:
        self.state_directory = state_directory
        self.active_path = state_directory / "active.json"
        self.snapshot_directory = state_directory / "snapshots"
        self.audit_path = state_directory / "changes.jsonl"

    def current(self) -> PilotRolloutConfig | None:
        if not self.active_path.exists():
            return None
        return load_pilot_rollout(self.active_path)

    def changes(self) -> list[PilotConfigChange]:
        if not self.audit_path.exists():
            return []
        return [
            PilotConfigChange.model_validate_json(line)
            for line in self.audit_path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]

    def activate(
        self,
        config: PilotRolloutConfig,
        *,
        actor_subject_digest: str,
        change_reference: str,
        changed_at: datetime,
    ) -> PilotConfigChange:
        return self._write_change(
            config,
            action=PilotChangeAction.ACTIVATE,
            actor_subject_digest=actor_subject_digest,
            change_reference=change_reference,
            changed_at=changed_at,
        )

    def rollback(
        self,
        target_digest: str,
        *,
        actor_subject_digest: str,
        change_reference: str,
        changed_at: datetime,
    ) -> PilotConfigChange:
        if len(target_digest) != 64 or any(
            character not in "0123456789abcdef" for character in target_digest
        ):
            raise ValueError("Rollback digest must be a lowercase SHA-256 value")
        snapshot_path = self.snapshot_directory / f"{target_digest}.json"
        if not snapshot_path.exists():
            raise ValueError("Rollback snapshot does not exist")
        target = load_pilot_rollout(snapshot_path)
        if pilot_config_digest(target) != target_digest:
            raise ValueError("Rollback snapshot digest mismatch")
        has_global_kill_switch = any(
            switch.enabled and switch.category is None and switch.cohort_id is None
            for switch in target.kill_switches
        )
        if target.mode != PilotMode.TECHNICAL_SHADOW and not has_global_kill_switch:
            raise ValueError("Rollback target must be technical shadow or retain a global kill switch")
        return self._write_change(
            target,
            action=PilotChangeAction.ROLLBACK,
            actor_subject_digest=actor_subject_digest,
            change_reference=change_reference,
            changed_at=changed_at,
        )

    def _write_change(
        self,
        config: PilotRolloutConfig,
        *,
        action: PilotChangeAction,
        actor_subject_digest: str,
        change_reference: str,
        changed_at: datetime,
    ) -> PilotConfigChange:
        if changed_at.tzinfo is None:
            raise ValueError("Pilot changes require a timezone-aware timestamp")
        previous = self.current()
        previous_digest = pilot_config_digest(previous) if previous else None
        active_digest = pilot_config_digest(config)
        self.snapshot_directory.mkdir(parents=True, exist_ok=True)
        snapshot_path = self.snapshot_directory / f"{active_digest}.json"
        serialized = pilot_config_json(config)
        if snapshot_path.exists():
            existing = load_pilot_rollout(snapshot_path)
            if pilot_config_digest(existing) != active_digest:
                raise ValueError("Existing pilot snapshot is corrupt")
        else:
            self._atomic_write(snapshot_path, serialized)
        self._atomic_write(self.active_path, serialized)
        change = PilotConfigChange(
            action=action,
            previous_digest=previous_digest,
            active_digest=active_digest,
            actor_subject_digest=actor_subject_digest,
            change_reference=change_reference,
            changed_at=changed_at,
        )
        with self.audit_path.open("a", encoding="utf-8") as stream:
            stream.write(change.model_dump_json() + "\n")
        return change

    @staticmethod
    def _atomic_write(path: Path, content: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(f"{path.suffix}.tmp")
        temporary.write_text(content, encoding="utf-8")
        temporary.replace(path)
