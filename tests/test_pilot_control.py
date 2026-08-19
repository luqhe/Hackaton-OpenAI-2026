from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

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
