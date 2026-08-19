from __future__ import annotations

import html
import json
from datetime import datetime
from enum import StrEnum
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from guardian_core.models import EnforcementAction, RiskAssessment, RiskCategory, RiskLevel
from risk_engine.calibration import VersionSet


class ShadowScope(StrEnum):
    SYNTHETIC_BASELINE = "SYNTHETIC_BASELINE"
    STAGING_COHORT = "STAGING_COHORT"


class HumanReview(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    reviewed: bool = False
    contested: bool = False
    reversed: bool = False
    final_risk: RiskLevel | None = None
    notes: str = Field(default="", max_length=500)

    @model_validator(mode="after")
    def validate_review(self) -> HumanReview:
        if (self.contested or self.reversed or self.final_risk is not None) and not self.reviewed:
            raise ValueError("Human outcomes require reviewed=true")
        if self.reversed and not self.contested:
            raise ValueError("A reversal must be associated with a contestation")
        return self


class ShadowRecord(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: str = "guardian.shadow-record.v1"
    window_id: str = Field(min_length=1, max_length=120)
    example_id: str = Field(min_length=1, max_length=120)
    observed_at: datetime
    context_digest: str = Field(min_length=64, max_length=64)
    application: str = Field(min_length=1, max_length=120)
    age_band: str = Field(min_length=1, max_length=20)
    versions: VersionSet
    local_assessment: RiskAssessment
    model_assessment: RiskAssessment
    policy_action: EnforcementAction
    simulated_action: EnforcementAction
    expected_risk: RiskLevel | None = None
    expected_category: RiskCategory | None = None
    human_review: HumanReview = Field(default_factory=HumanReview)
    actual_intervention: Literal[False] = False


class ShadowSummary(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: str = "guardian.shadow-summary.v1"
    window_id: str
    records: int
    reviewed_records: int
    local_model_disagreements: int
    model_policy_disagreements: int
    policy_human_disagreements: int
    false_positives: int
    false_negatives: int
    false_positive_rate: float
    false_negative_rate: float
    contestation_rate: float
    reversal_rate: float
    actual_interventions: int
    by_category: dict[str, dict[str, int]]
    by_model_version: dict[str, int]


class ShadowWindowResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: str = "guardian.shadow-window.v1"
    window_id: str
    scope: ShadowScope
    category: RiskCategory
    versions: VersionSet
    minimum_samples: int
    category_samples: int
    maximum_false_positive_rate: float
    observed_false_positive_rate: float
    stable: bool
    release_eligible: bool
    reason: str


class ShadowStore:
    """Append-only JSONL audit store; raw observed content is intentionally excluded."""

    def __init__(self, path: Path) -> None:
        self.path = path

    def append(self, record: ShadowRecord) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as stream:
            stream.write(record.model_dump_json() + "\n")

    def load(self) -> list[ShadowRecord]:
        if not self.path.exists():
            return []
        return [
            ShadowRecord.model_validate_json(line)
            for line in self.path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]


def summarize_shadow(records: list[ShadowRecord]) -> ShadowSummary:
    if not records:
        raise ValueError("Cannot summarize an empty shadow window")
    window_ids = {record.window_id for record in records}
    if len(window_ids) != 1:
        raise ValueError("A summary can cover only one shadow window")

    false_positives = false_negatives = expected_safe = expected_unsafe = 0
    local_model_disagreements = model_policy_disagreements = policy_human_disagreements = 0
    reviewed = contested = reversed_count = actual_interventions = 0
    by_category: dict[str, dict[str, int]] = {}
    by_model: dict[str, int] = {}

    for record in records:
        model_positive = record.model_assessment.risk != RiskLevel.SAFE
        if record.expected_risk is not None:
            expected_positive = record.expected_risk != RiskLevel.SAFE
            if expected_positive:
                expected_unsafe += 1
                false_negatives += int(not model_positive)
            else:
                expected_safe += 1
                false_positives += int(model_positive)
        local_model_disagreements += int(record.local_assessment != record.model_assessment)
        expected_policy_action = EnforcementAction.IGNORE if not model_positive else record.simulated_action
        model_policy_disagreements += int(record.policy_action != expected_policy_action)
        reviewed += int(record.human_review.reviewed)
        contested += int(record.human_review.contested)
        reversed_count += int(record.human_review.reversed)
        actual_interventions += int(record.actual_intervention)
        if record.human_review.final_risk is not None:
            human_positive = record.human_review.final_risk != RiskLevel.SAFE
            policy_positive = record.policy_action != EnforcementAction.IGNORE
            policy_human_disagreements += int(human_positive != policy_positive)

        category = (
            record.expected_category.value
            if record.expected_category
            else record.model_assessment.category.value
            if record.model_assessment.category
            else "SAFE"
        )
        bucket = by_category.setdefault(category, {"records": 0, "false_positives": 0, "false_negatives": 0})
        bucket["records"] += 1
        if record.expected_risk == RiskLevel.SAFE and model_positive:
            bucket["false_positives"] += 1
        if record.expected_risk not in {None, RiskLevel.SAFE} and not model_positive:
            bucket["false_negatives"] += 1
        by_model[record.versions.model] = by_model.get(record.versions.model, 0) + 1

    simulated_blocks = sum(record.simulated_action == EnforcementAction.BLOCK for record in records)
    return ShadowSummary(
        window_id=records[0].window_id,
        records=len(records),
        reviewed_records=reviewed,
        local_model_disagreements=local_model_disagreements,
        model_policy_disagreements=model_policy_disagreements,
        policy_human_disagreements=policy_human_disagreements,
        false_positives=false_positives,
        false_negatives=false_negatives,
        false_positive_rate=false_positives / expected_safe if expected_safe else 0.0,
        false_negative_rate=false_negatives / expected_unsafe if expected_unsafe else 0.0,
        contestation_rate=contested / reviewed if reviewed else 0.0,
        reversal_rate=reversed_count / simulated_blocks if simulated_blocks else 0.0,
        actual_interventions=actual_interventions,
        by_category=dict(sorted(by_category.items())),
        by_model_version=dict(sorted(by_model.items())),
    )


def evaluate_shadow_window(
    records: list[ShadowRecord],
    *,
    scope: ShadowScope,
    category: RiskCategory,
    versions: VersionSet,
    minimum_samples: int,
    maximum_false_positive_rate: float,
) -> ShadowWindowResult:
    matching = [
        record
        for record in records
        if record.versions == versions
        and (record.expected_category == category or record.model_assessment.category == category)
    ]
    relevant_safe = [record for record in records if record.expected_risk == RiskLevel.SAFE]
    false_positives = sum(record.model_assessment.category == category for record in relevant_safe)
    observed_rate = false_positives / len(relevant_safe) if relevant_safe else 0.0
    stable = len(matching) >= minimum_samples and observed_rate <= maximum_false_positive_rate
    release_eligible = stable and scope == ShadowScope.STAGING_COHORT
    if not stable:
        reason = "Shadow window does not meet sample or false-positive requirements"
    elif scope != ShadowScope.STAGING_COHORT:
        reason = "Synthetic baseline is reproducible but cannot authorize a real intervention"
    else:
        reason = "Exact category/version staging window meets the configured shadow gate"
    return ShadowWindowResult(
        window_id=records[0].window_id if records else "empty",
        scope=scope,
        category=category,
        versions=versions,
        minimum_samples=minimum_samples,
        category_samples=len(matching),
        maximum_false_positive_rate=maximum_false_positive_rate,
        observed_false_positive_rate=observed_rate,
        stable=stable,
        release_eligible=release_eligible,
        reason=reason,
    )


def render_shadow_dashboard(summary: ShadowSummary) -> str:
    category_rows = "".join(
        "<tr>"
        f"<td>{html.escape(category)}</td>"
        f"<td>{values['records']}</td>"
        f"<td>{values['false_positives']}</td>"
        f"<td>{values['false_negatives']}</td>"
        "</tr>"
        for category, values in summary.by_category.items()
    )
    return f"""<!doctype html>
<html lang="pt-BR">
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Guardian — Shadow QA</title>
<style>body{{font:16px system-ui;margin:2rem;max-width:900px;color:#17202a}}.grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(160px,1fr));gap:12px}}.card{{border:1px solid #d8dee4;border-radius:12px;padding:16px}}table{{border-collapse:collapse;width:100%;margin-top:20px}}th,td{{padding:10px;border-bottom:1px solid #d8dee4;text-align:left}}small{{color:#57606a}}</style>
</head><body>
<h1>Shadow QA</h1><p><small>Janela {html.escape(summary.window_id)} · relatório interno; não é a funcionalidade principal do produto.</small></p>
<div class="grid"><div class="card"><strong>{summary.records}</strong><br>registros simulados</div><div class="card"><strong>{summary.false_positives}</strong><br>falsos positivos</div><div class="card"><strong>{summary.false_negatives}</strong><br>falsos negativos</div><div class="card"><strong>{summary.actual_interventions}</strong><br>intervenções reais</div></div>
<table><thead><tr><th>Categoria</th><th>Casos</th><th>FP revisados</th><th>FN revisados</th></tr></thead><tbody>{category_rows}</tbody></table>
<p>Contestação: {summary.contestation_rate:.1%} · reversão: {summary.reversal_rate:.1%} · divergências local/modelo: {summary.local_model_disagreements}</p>
</body></html>"""


def summary_as_pretty_json(summary: ShadowSummary) -> str:
    return json.dumps(summary.model_dump(mode="json"), indent=2, ensure_ascii=False) + "\n"
