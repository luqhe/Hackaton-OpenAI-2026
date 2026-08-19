from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest
from pydantic import ValidationError

from guardian_core.models import EnforcementAction, RiskCategory
from risk_engine.engine import assess_risk
from risk_engine.evaluation import (
    evaluate_dataset,
    load_dataset,
    load_regression_gate,
    regression_failures,
)
from risk_engine.shadow import (
    ShadowRecord,
    ShadowScope,
    ShadowStore,
    evaluate_shadow_window,
    render_shadow_dashboard,
    summarize_shadow,
)
from scripts.run_r3_evals import DATASET_PATH, GATE_PATH, VERSIONS, build_shadow_records


def test_dataset_is_synthetic_versioned_and_split_without_identifier_leakage() -> None:
    examples, digest = load_dataset(DATASET_PATH)

    assert len(examples) >= 30
    assert len(digest) == 64
    assert {example.split for example in examples} == {"development", "calibration", "test"}
    assert all(example.rights == "project-owned-synthetic" for example in examples)
    split_by_id = {example.id: example.split for example in examples}
    assert len(split_by_id) == len(examples)


def test_frozen_regression_reports_required_slices_and_passes_gate() -> None:
    report = evaluate_dataset(
        DATASET_PATH,
        assess_risk,
        versions=VERSIONS,
        evaluation_version="test-run",
        split="test",
    )
    gate = load_regression_gate(GATE_PATH)

    assert regression_failures(report, gate) == []
    assert set(report.by_category) >= {"SAFE", "DANGEROUS_CONTACT", "ADULT_CONTENT", "HATE_SPEECH"}
    assert set(report.by_direction) >= {
        "NONE",
        "CONTENT_CONSUMPTION",
        "CHILD_AS_TARGET",
        "CHILD_AS_ACTOR",
    }
    assert len(report.by_age_band) == 4
    assert len(report.by_application) >= 4


def test_invalid_classifier_output_fails_frozen_regression() -> None:
    report = evaluate_dataset(
        DATASET_PATH,
        lambda observation: {"risk": "HIGH"},
        versions=VERSIONS,
        evaluation_version="broken",
        split="test",
    )

    assert report.invalid_output_rate == 1
    assert regression_failures(report, load_regression_gate(GATE_PATH))


def test_shadow_mode_compares_layers_and_never_intervenes() -> None:
    records = build_shadow_records()
    summary = summarize_shadow(records)

    assert summary.records >= 10
    assert summary.reviewed_records == summary.records
    assert summary.actual_interventions == 0
    assert summary.contestation_rate == 0
    assert "falsos positivos" in render_shadow_dashboard(summary)


def test_synthetic_shadow_window_is_stable_but_cannot_approve_release() -> None:
    records = build_shadow_records()
    result = evaluate_shadow_window(
        records,
        scope=ShadowScope.SYNTHETIC_BASELINE,
        category=RiskCategory.DANGEROUS_CONTACT,
        versions=VERSIONS,
        minimum_samples=2,
        maximum_false_positive_rate=0.1,
    )

    assert result.stable is True
    assert result.release_eligible is False
    assert "cannot authorize" in result.reason


def test_shadow_record_forbids_actual_intervention_and_store_is_append_only(
    tmp_path: Path,
) -> None:
    record = build_shadow_records()[0]
    with pytest.raises(ValidationError):
        ShadowRecord.model_validate({**record.model_dump(mode="json"), "actual_intervention": True})

    store = ShadowStore(tmp_path / "shadow.jsonl")
    store.append(record)
    loaded = store.load()
    assert loaded == [record]
    assert loaded[0].observed_at.tzinfo == UTC


def test_review_metrics_measure_contestation_and_reversal() -> None:
    record = build_shadow_records()[0]
    contested = record.model_copy(
        update={
            "example_id": "reviewed-reversal",
            "observed_at": datetime(2026, 8, 20, tzinfo=UTC),
            "simulated_action": EnforcementAction.BLOCK,
            "human_review": record.human_review.model_copy(update={"contested": True, "reversed": True}),
        }
    )
    summary = summarize_shadow([contested])

    assert summary.contestation_rate == 1
    assert summary.reversal_rate == 1
