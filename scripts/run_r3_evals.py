from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from guardian_core.models import EnforcementAction, RiskLevel  # noqa: E402
from risk_engine.calibration import VersionSet  # noqa: E402
from risk_engine.context import build_context  # noqa: E402
from risk_engine.engine import assess_risk  # noqa: E402
from risk_engine.evaluation import (  # noqa: E402
    evaluate_dataset,
    load_dataset,
    load_regression_gate,
    regression_failures,
    report_as_pretty_json,
)
from risk_engine.shadow import (  # noqa: E402
    HumanReview,
    ShadowRecord,
    ShadowScope,
    evaluate_shadow_window,
    render_shadow_dashboard,
    summarize_shadow,
    summary_as_pretty_json,
)

DATASET_PATH = PROJECT_ROOT / "evals" / "dataset-v1.jsonl"
GATE_PATH = PROJECT_ROOT / "evals" / "regression-gate.v1.json"
RESULTS_DIRECTORY = PROJECT_ROOT / "evals" / "results"
VERSIONS = VersionSet(
    model="heuristic-context-v1",
    prompt="heuristic-rules.v1",
    dataset="guardian-synthetic-context-v1.0.0",
)


def _action_for_risk(risk: RiskLevel) -> EnforcementAction:
    if risk == RiskLevel.SAFE:
        return EnforcementAction.IGNORE
    if risk == RiskLevel.HIGH:
        return EnforcementAction.BLOCK
    return EnforcementAction.ALERT


def build_shadow_records() -> list[ShadowRecord]:
    examples, _ = load_dataset(DATASET_PATH)
    test_examples = [example for example in examples if example.split == "test"]
    started_at = datetime(2026, 8, 19, tzinfo=UTC)
    records: list[ShadowRecord] = []
    for index, example in enumerate(test_examples):
        observation = example.observation()
        assessment = assess_risk(observation)
        simulated_action = _action_for_risk(assessment.risk)
        mismatch = (
            assessment.risk != example.expected_risk or assessment.category != example.expected_category
        )
        records.append(
            ShadowRecord(
                window_id="synthetic-r3-baseline-v1",
                example_id=example.id,
                observed_at=started_at + timedelta(minutes=index),
                context_digest=build_context(observation).context_digest,
                application=example.application,
                age_band=example.age_band,
                versions=VERSIONS,
                local_assessment=assessment,
                model_assessment=assessment,
                policy_action=simulated_action,
                simulated_action=simulated_action,
                expected_risk=example.expected_risk,
                expected_category=example.expected_category,
                human_review=HumanReview(
                    reviewed=True,
                    contested=mismatch,
                    reversed=mismatch and simulated_action == EnforcementAction.BLOCK,
                    final_risk=example.expected_risk,
                    notes="Synthetic ground truth from frozen R3 dataset.",
                ),
            )
        )
    return records


def run(*, write_results: bool) -> list[str]:
    report = evaluate_dataset(
        DATASET_PATH,
        assess_risk,
        versions=VERSIONS,
        evaluation_version="heuristic-context-v1__guardian-synthetic-context-v1.0.0",
        split="test",
    )
    gate = load_regression_gate(GATE_PATH)
    failures = regression_failures(report, gate)

    records = build_shadow_records()
    summary = summarize_shadow(records)
    if summary.actual_interventions:
        failures.append("Shadow mode performed an actual intervention")

    window_results = [
        evaluate_shadow_window(
            records,
            scope=ShadowScope.SYNTHETIC_BASELINE,
            category=category,
            versions=VERSIONS,
            minimum_samples=2,
            maximum_false_positive_rate=0.1,
        )
        for category in gate.minimum_category_precision
    ]
    if any(window.release_eligible for window in window_results):
        failures.append("A synthetic shadow window incorrectly became release-eligible")

    if write_results:
        RESULTS_DIRECTORY.mkdir(parents=True, exist_ok=True)
        (RESULTS_DIRECTORY / "eval-report.v1.json").write_text(
            report_as_pretty_json(report), encoding="utf-8"
        )
        (RESULTS_DIRECTORY / "shadow-summary.v1.json").write_text(
            summary_as_pretty_json(summary), encoding="utf-8"
        )
        (RESULTS_DIRECTORY / "shadow-dashboard.v1.html").write_text(
            render_shadow_dashboard(summary), encoding="utf-8"
        )
        (RESULTS_DIRECTORY / "shadow-windows.v1.json").write_text(
            json.dumps(
                [window.model_dump(mode="json") for window in window_results],
                indent=2,
                ensure_ascii=False,
            )
            + "\n",
            encoding="utf-8",
        )
        digest = hashlib.sha256(DATASET_PATH.read_bytes()).hexdigest()
        print(f"results={RESULTS_DIRECTORY} dataset_sha256={digest}")
    return failures


def main() -> int:
    parser = argparse.ArgumentParser(description="Run Guardian R3 frozen eval and shadow baseline")
    parser.add_argument(
        "--check",
        action="store_true",
        help="Validate the frozen gate without rewriting versioned reports",
    )
    args = parser.parse_args()
    failures = run(write_results=not args.check)
    if failures:
        for failure in failures:
            print(f"R3 regression failure: {failure}")
        return 1
    print("R3 eval and shadow gates passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
