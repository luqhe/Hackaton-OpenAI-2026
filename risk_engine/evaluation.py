from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from collections.abc import Callable, Iterable
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from guardian_core.models import (
    ConversationMessage,
    Observation,
    RiskAssessment,
    RiskCategory,
    RiskDirection,
    RiskLevel,
)
from risk_engine.calibration import VersionSet


class EvalExample(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1, max_length=100)
    split: Literal["development", "calibration", "test"]
    age_band: Literal["6-9", "10-12", "13-15", "16-17"]
    application: str = Field(min_length=1, max_length=120)
    language: str = Field(min_length=2, max_length=10)
    window_title: str = Field(default="", max_length=500)
    visible_text: str = Field(default="", max_length=20_000)
    messages: list[ConversationMessage] = Field(default_factory=list, max_length=10)
    expected_risk: RiskLevel
    expected_category: RiskCategory | None = None
    expected_direction: RiskDirection | None = None
    context_kind: str = Field(min_length=1, max_length=80)
    rights: Literal["project-owned-synthetic"]
    notes: str = Field(default="", max_length=500)

    @model_validator(mode="after")
    def validate_expected_semantics(self) -> EvalExample:
        if self.expected_risk == RiskLevel.SAFE:
            if self.expected_category is not None or self.expected_direction is not None:
                raise ValueError("SAFE examples cannot have an expected category or direction")
        elif self.expected_category is None or self.expected_direction is None:
            raise ValueError("Non-SAFE examples require an expected category and direction")
        return self

    def observation(self) -> Observation:
        return Observation(
            app_name=self.application,
            window_title=self.window_title,
            visible_text=self.visible_text,
            recent_messages=self.messages,
        )


class MetricSlice(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    support: int
    true_positive: int
    false_positive: int
    true_negative: int
    false_negative: int
    precision: float
    recall: float
    false_positive_rate: float
    risk_accuracy: float
    category_accuracy: float
    direction_accuracy: float


class EvaluationReport(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: str = "guardian.eval-report.v1"
    evaluation_version: str
    versions: VersionSet
    dataset_sha256: str
    split: str
    examples: int
    invalid_outputs: int
    invalid_output_rate: float
    overall: MetricSlice
    by_category: dict[str, MetricSlice]
    by_age_band: dict[str, MetricSlice]
    by_application: dict[str, MetricSlice]
    by_direction: dict[str, MetricSlice]


class RegressionGate(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: str = "guardian.eval-gate.v1"
    gate_version: str
    dataset_version: str
    dataset_sha256: str = Field(min_length=64, max_length=64)
    model_version: str
    prompt_version: str
    split: Literal["test"] = "test"
    minimum_precision: float = Field(ge=0, le=1)
    minimum_recall: float = Field(ge=0, le=1)
    maximum_false_positive_rate: float = Field(ge=0, le=1)
    maximum_invalid_output_rate: float = Field(ge=0, le=1)
    minimum_category_precision: dict[RiskCategory, float]


def load_dataset(path: Path) -> tuple[list[EvalExample], str]:
    raw = path.read_bytes()
    canonical_raw = raw.replace(b"\r\n", b"\n").replace(b"\r", b"\n")
    examples: list[EvalExample] = []
    for line_number, line in enumerate(canonical_raw.decode("utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            examples.append(EvalExample.model_validate_json(line))
        except Exception as error:
            raise ValueError(f"Invalid dataset example on line {line_number}") from error
    if not examples:
        raise ValueError("Evaluation dataset is empty")
    identifiers = [example.id for example in examples]
    if len(identifiers) != len(set(identifiers)):
        raise ValueError("Evaluation dataset contains duplicate IDs")
    present_splits = {example.split for example in examples}
    if present_splits != {"development", "calibration", "test"}:
        raise ValueError("Dataset must contain development, calibration and test splits")
    return examples, hashlib.sha256(canonical_raw).hexdigest()


def _metric_slice(
    pairs: Iterable[tuple[EvalExample, RiskAssessment | None]],
    *,
    expected_positive: Callable[[EvalExample], bool] | None = None,
    predicted_positive: Callable[[RiskAssessment], bool] | None = None,
) -> MetricSlice:
    materialized = list(pairs)
    true_positive = false_positive = true_negative = false_negative = 0
    exact_risk = exact_category = exact_direction = expected_category_total = 0
    expected_test = expected_positive or (lambda example: example.expected_risk != RiskLevel.SAFE)
    predicted_test = predicted_positive or (lambda prediction: prediction.risk != RiskLevel.SAFE)
    for example, prediction in materialized:
        expected_is_positive = expected_test(example)
        predicted_is_positive = prediction is not None and predicted_test(prediction)
        if expected_is_positive and predicted_is_positive:
            true_positive += 1
        elif expected_is_positive:
            false_negative += 1
        elif predicted_is_positive:
            false_positive += 1
        else:
            true_negative += 1
        if prediction is not None and prediction.risk == example.expected_risk:
            exact_risk += 1
        if expected_positive:
            expected_category_total += 1
            if prediction is not None and prediction.category == example.expected_category:
                exact_category += 1
            if prediction is not None and prediction.direction == example.expected_direction:
                exact_direction += 1

    total = len(materialized)
    predicted_positives = true_positive + false_positive
    actual_positives = true_positive + false_negative
    actual_negatives = true_negative + false_positive
    return MetricSlice(
        support=total,
        true_positive=true_positive,
        false_positive=false_positive,
        true_negative=true_negative,
        false_negative=false_negative,
        precision=true_positive / predicted_positives if predicted_positives else 1.0,
        recall=true_positive / actual_positives if actual_positives else 1.0,
        false_positive_rate=false_positive / actual_negatives if actual_negatives else 0.0,
        risk_accuracy=exact_risk / total if total else 0.0,
        category_accuracy=(exact_category / expected_category_total if expected_category_total else 1.0),
        direction_accuracy=(exact_direction / expected_category_total if expected_category_total else 1.0),
    )


def _group_metrics(
    pairs: list[tuple[EvalExample, RiskAssessment | None]],
    key: Callable[[EvalExample], str],
) -> dict[str, MetricSlice]:
    grouped: dict[str, list[tuple[EvalExample, RiskAssessment | None]]] = defaultdict(list)
    for pair in pairs:
        grouped[key(pair[0])].append(pair)
    return {name: _metric_slice(items) for name, items in sorted(grouped.items())}


def _category_metrics(
    pairs: list[tuple[EvalExample, RiskAssessment | None]],
) -> dict[str, MetricSlice]:
    metrics = {
        category.value: _metric_slice(
            pairs,
            expected_positive=lambda example, current=category: example.expected_category == current,
            predicted_positive=lambda prediction, current=category: prediction.category == current,
        )
        for category in RiskCategory
    }
    metrics["SAFE"] = _metric_slice(
        pairs,
        expected_positive=lambda example: example.expected_risk == RiskLevel.SAFE,
        predicted_positive=lambda prediction: prediction.risk == RiskLevel.SAFE,
    )
    return dict(sorted(metrics.items()))


def _direction_metrics(
    pairs: list[tuple[EvalExample, RiskAssessment | None]],
) -> dict[str, MetricSlice]:
    metrics = {
        direction.value: _metric_slice(
            pairs,
            expected_positive=lambda example, current=direction: example.expected_direction == current,
            predicted_positive=lambda prediction, current=direction: prediction.direction == current,
        )
        for direction in RiskDirection
    }
    metrics["NONE"] = _metric_slice(
        pairs,
        expected_positive=lambda example: example.expected_direction is None,
        predicted_positive=lambda prediction: prediction.direction is None,
    )
    return dict(sorted(metrics.items()))


def evaluate_dataset(
    dataset_path: Path,
    classifier: Callable[[Observation], RiskAssessment],
    *,
    versions: VersionSet,
    evaluation_version: str,
    split: Literal["development", "calibration", "test"] = "test",
) -> EvaluationReport:
    examples, dataset_hash = load_dataset(dataset_path)
    selected = [example for example in examples if example.split == split]
    pairs: list[tuple[EvalExample, RiskAssessment | None]] = []
    invalid_outputs = 0
    for example in selected:
        try:
            prediction = RiskAssessment.model_validate(classifier(example.observation()))
        except Exception:
            prediction = None
            invalid_outputs += 1
        pairs.append((example, prediction))

    return EvaluationReport(
        evaluation_version=evaluation_version,
        versions=versions,
        dataset_sha256=dataset_hash,
        split=split,
        examples=len(selected),
        invalid_outputs=invalid_outputs,
        invalid_output_rate=invalid_outputs / len(selected) if selected else 0.0,
        overall=_metric_slice(pairs),
        by_category=_category_metrics(pairs),
        by_age_band=_group_metrics(pairs, lambda item: item.age_band),
        by_application=_group_metrics(pairs, lambda item: item.application),
        by_direction=_direction_metrics(pairs),
    )


def load_regression_gate(path: Path) -> RegressionGate:
    return RegressionGate.model_validate_json(path.read_text(encoding="utf-8"))


def regression_failures(report: EvaluationReport, gate: RegressionGate) -> list[str]:
    failures: list[str] = []
    if report.versions.dataset != gate.dataset_version:
        failures.append("Dataset version does not match the frozen regression gate")
    if report.dataset_sha256 != gate.dataset_sha256:
        failures.append("Dataset content changed without a new frozen regression gate")
    if report.versions.model != gate.model_version:
        failures.append("Model version does not match the frozen regression gate")
    if report.versions.prompt != gate.prompt_version:
        failures.append("Prompt version does not match the frozen regression gate")
    if report.split != gate.split:
        failures.append("Regression gate must run only on the frozen final test split")
    if report.overall.precision < gate.minimum_precision:
        failures.append("Overall precision is below the regression floor")
    if report.overall.recall < gate.minimum_recall:
        failures.append("Overall recall is below the regression floor")
    if report.overall.false_positive_rate > gate.maximum_false_positive_rate:
        failures.append("False-positive rate exceeds the regression ceiling")
    if report.invalid_output_rate > gate.maximum_invalid_output_rate:
        failures.append("Invalid-output rate exceeds the regression ceiling")
    for category, minimum in gate.minimum_category_precision.items():
        metric = report.by_category.get(category.value)
        if metric is None or metric.precision < minimum:
            failures.append(f"{category.value} precision is below the regression floor")
    return failures


def report_as_pretty_json(report: EvaluationReport) -> str:
    return json.dumps(report.model_dump(mode="json"), indent=2, ensure_ascii=False) + "\n"
