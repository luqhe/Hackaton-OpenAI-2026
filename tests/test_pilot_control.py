from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest
from pydantic import ValidationError

from guardian_core.pilot import PilotMode, load_pilot_rollout
from guardian_core.pilot_control import PilotChangeAction, PilotConfigStore, pilot_config_digest

ROOT = Path(__file__).resolve().parents[1]
BASELINE_PATH = ROOT / "config" / "pilot-rollout.v1.json"
NOW = datetime(2026, 8, 20, 18, tzinfo=UTC)
ACTOR_DIGEST = "c" * 64


def test_activation_and_rollback_are_versioned_and_audited(tmp_path: Path) -> None:
    store = PilotConfigStore(tmp_path / "pilot-state")
    baseline = load_pilot_rollout(BASELINE_PATH)
    initial = store.activate(
        baseline,
        actor_subject_digest=ACTOR_DIGEST,
        change_reference="PILOT-100",
        changed_at=NOW,
    )
    permissive = baseline.model_copy(update={"mode": PilotMode.ALERT_ONLY, "kill_switches": ()})
    promoted = store.activate(
        permissive,
        actor_subject_digest=ACTOR_DIGEST,
        change_reference="PILOT-101",
        changed_at=NOW,
    )

    rolled_back = store.rollback(
        initial.active_digest,
        actor_subject_digest=ACTOR_DIGEST,
        change_reference="INC-42",
        changed_at=NOW,
    )

    assert promoted.previous_digest == initial.active_digest
    assert rolled_back.action == PilotChangeAction.ROLLBACK
    assert rolled_back.previous_digest == promoted.active_digest
    assert store.current() == baseline
    assert store.changes() == [initial, promoted, rolled_back]


def test_rollback_rejects_unknown_or_less_safe_snapshot(tmp_path: Path) -> None:
    store = PilotConfigStore(tmp_path / "pilot-state")
    baseline = load_pilot_rollout(BASELINE_PATH)
    unsafe = baseline.model_copy(update={"mode": PilotMode.ALERT_ONLY, "kill_switches": ()})
    unsafe_change = store.activate(
        unsafe,
        actor_subject_digest=ACTOR_DIGEST,
        change_reference="PILOT-unsafe-test",
        changed_at=NOW,
    )

    with pytest.raises(ValueError, match="retain a global kill switch"):
        store.rollback(
            unsafe_change.active_digest,
            actor_subject_digest=ACTOR_DIGEST,
            change_reference="INC-43",
            changed_at=NOW,
        )
    with pytest.raises(ValueError, match="does not exist"):
        store.rollback(
            "0" * 64,
            actor_subject_digest=ACTOR_DIGEST,
            change_reference="INC-44",
            changed_at=NOW,
        )


def test_tampered_snapshot_fails_digest_validation(tmp_path: Path) -> None:
    store = PilotConfigStore(tmp_path / "pilot-state")
    baseline = load_pilot_rollout(BASELINE_PATH)
    change = store.activate(
        baseline,
        actor_subject_digest=ACTOR_DIGEST,
        change_reference="PILOT-102",
        changed_at=NOW,
    )
    snapshot = store.snapshot_directory / f"{change.active_digest}.json"
    replacement = baseline.model_copy(update={"rollout_id": "tampered"})
    snapshot.write_text(replacement.model_dump_json(), encoding="utf-8")

    with pytest.raises(ValueError, match="digest mismatch"):
        store.rollback(
            change.active_digest,
            actor_subject_digest=ACTOR_DIGEST,
            change_reference="INC-45",
            changed_at=NOW,
        )

    assert pilot_config_digest(replacement) != change.active_digest


def test_invalid_audit_fields_do_not_mutate_active_state(tmp_path: Path) -> None:
    store = PilotConfigStore(tmp_path / "pilot-state")
    baseline = load_pilot_rollout(BASELINE_PATH)
    initial = store.activate(
        baseline,
        actor_subject_digest=ACTOR_DIGEST,
        change_reference="PILOT-200",
        changed_at=NOW,
    )
    active_before = store.active_path.read_bytes()
    audit_before = store.audit_path.read_bytes()

    with pytest.raises(ValidationError):
        store.activate(
            baseline.model_copy(update={"rollout_id": "invalid-actor-change"}),
            actor_subject_digest="not-a-digest",
            change_reference="PILOT-201",
            changed_at=NOW,
        )

    assert store.active_path.read_bytes() == active_before
    assert store.audit_path.read_bytes() == audit_before
    assert store.changes() == [initial]


def test_partial_write_failure_restores_snapshot_audit_and_active(monkeypatch, tmp_path: Path) -> None:
    store = PilotConfigStore(tmp_path / "pilot-state")
    baseline = load_pilot_rollout(BASELINE_PATH)
    store.activate(
        baseline,
        actor_subject_digest=ACTOR_DIGEST,
        change_reference="PILOT-202",
        changed_at=NOW,
    )
    active_before = store.active_path.read_bytes()
    audit_before = store.audit_path.read_bytes()
    promoted = baseline.model_copy(update={"rollout_id": "promotion-that-fails"})
    promoted_snapshot = store.snapshot_directory / f"{pilot_config_digest(promoted)}.json"
    original_write = store._atomic_write

    def fail_active(path: Path, content: str) -> None:
        if path == store.active_path:
            raise OSError("simulated active write failure")
        original_write(path, content)

    monkeypatch.setattr(store, "_atomic_write", fail_active)
    with pytest.raises(OSError, match="simulated"):
        store.activate(
            promoted,
            actor_subject_digest=ACTOR_DIGEST,
            change_reference="PILOT-203",
            changed_at=NOW,
        )

    assert store.active_path.read_bytes() == active_before
    assert store.audit_path.read_bytes() == audit_before
    assert not promoted_snapshot.exists()
