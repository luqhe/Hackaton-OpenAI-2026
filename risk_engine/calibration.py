from __future__ import annotations

import json
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from guardian_core.models import (
    EnforcementAction,
    PolicyDecision,
    RiskAssessment,
    RiskCategory,
    RiskLevel,
)
from risk_engine.contracts import CLASSIFIER_INTERFACE_VERSION
from risk_engine.pipeline import PipelineResult


class VersionSet(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    classifier_interface: str = CLASSIFIER_INTERFACE_VERSION
    model: str
    prompt: str
    dataset: str


class CalibrationPoint(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    raw: float = Field(ge=0, le=1)
    calibrated: float = Field(ge=0, le=1)


class CategoryControls(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    calibration: tuple[CalibrationPoint, ...]
    log_threshold: float = Field(ge=0, le=1)
    alert_threshold: float = Field(ge=0, le=1)
    block_threshold: float = Field(ge=0, le=1)

    @model_validator(mode="after")
    def validate_ordering(self) -> CategoryControls:
        if not self.log_threshold < self.alert_threshold < self.block_threshold:
            raise ValueError("Thresholds must be strictly ordered LOG < ALERT < BLOCK")
        if len(self.calibration) < 2:
            raise ValueError("A calibration curve requires at least two points")
        raw_values = [point.raw for point in self.calibration]
        calibrated_values = [point.calibrated for point in self.calibration]
        if raw_values != sorted(raw_values) or len(set(raw_values)) != len(raw_values):
            raise ValueError("Calibration raw scores must be strictly increasing")
        if calibrated_values != sorted(calibrated_values):
            raise ValueError("Calibration output must be monotonic")
        return self


class KillSwitch(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    category: RiskCategory
    model_version: str = "*"
    enabled: bool = True
    reason: str = Field(min_length=1, max_length=500)


class BlockApproval(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    category: RiskCategory
    versions: VersionSet
    shadow_window_id: str = Field(min_length=1, max_length=120)
    shadow_scope: Literal["STAGING_COHORT"] = "STAGING_COHORT"
    shadow_gate_passed: bool
    product_safety_approved: bool
    engineering_approved: bool

    @property
    def approved(self) -> bool:
        return self.shadow_gate_passed and self.product_safety_approved and self.engineering_approved


class RiskControlConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: str = "guardian.risk-controls.v1"
    controls_version: str
    categories: dict[RiskCategory, CategoryControls]
    kill_switches: tuple[KillSwitch, ...] = ()
    block_approvals: tuple[BlockApproval, ...] = ()

    def category(self, category: RiskCategory) -> CategoryControls:
        try:
            return self.categories[category]
        except KeyError as error:
            raise ValueError(f"Missing controls for {category}") from error


class RiskControlDecision(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    maximum_action: EnforcementAction
    calibrated_confidence: float = Field(ge=0, le=1)
    ambiguous: bool
    block_gate_approved: bool
    kill_switch_active: bool
    reason: str


ACTION_ORDER = {
    EnforcementAction.IGNORE: 0,
    EnforcementAction.LOG: 1,
    EnforcementAction.ALERT: 2,
    EnforcementAction.BLOCK: 3,
}


def load_controls(path: Path) -> RiskControlConfig:
    return RiskControlConfig.model_validate_json(path.read_text(encoding="utf-8"))


def calibrate_confidence(raw: float, controls: CategoryControls) -> float:
    points = controls.calibration
    if raw <= points[0].raw:
        return points[0].calibrated
    if raw >= points[-1].raw:
        return points[-1].calibrated
    for left, right in zip(points, points[1:], strict=False):
        if left.raw <= raw <= right.raw:
            distance = (raw - left.raw) / (right.raw - left.raw)
            return left.calibrated + distance * (right.calibrated - left.calibrated)
    raise AssertionError("Calibration curve did not cover the score")


def _kill_switch_active(
    config: RiskControlConfig,
    category: RiskCategory,
    model_version: str,
) -> bool:
    return any(
        switch.enabled and switch.category == category and switch.model_version in {"*", model_version}
        for switch in config.kill_switches
    )


def _block_gate_approved(
    config: RiskControlConfig,
    category: RiskCategory,
    versions: VersionSet,
) -> bool:
    return any(
        approval.category == category and approval.versions == versions and approval.approved
        for approval in config.block_approvals
    )


def evaluate_risk_controls(
    assessment: RiskAssessment,
    *,
    versions: VersionSet,
    config: RiskControlConfig,
    pipeline_block_eligible: bool,
) -> RiskControlDecision:
    if assessment.risk == RiskLevel.SAFE or assessment.category is None:
        return RiskControlDecision(
            maximum_action=EnforcementAction.IGNORE,
            calibrated_confidence=assessment.confidence,
            ambiguous=False,
            block_gate_approved=False,
            kill_switch_active=False,
            reason="SAFE assessments cannot trigger an intervention",
        )

    category_controls = config.category(assessment.category)
    calibrated = calibrate_confidence(assessment.confidence, category_controls)
    kill_switch = _kill_switch_active(config, assessment.category, versions.model)
    block_approved = _block_gate_approved(config, assessment.category, versions)
    ambiguous = category_controls.log_threshold <= calibrated < category_controls.block_threshold

    if calibrated < category_controls.log_threshold:
        maximum = EnforcementAction.IGNORE
        reason = "Confidence is below the LOG threshold"
    elif calibrated < category_controls.alert_threshold or assessment.risk == RiskLevel.LOW:
        maximum = EnforcementAction.LOG
        reason = "Signal is in the low-confidence review band"
    elif calibrated < category_controls.block_threshold or assessment.risk != RiskLevel.HIGH:
        maximum = EnforcementAction.ALERT
        reason = "Signal is in the ambiguous no-auto-block band"
    elif not pipeline_block_eligible:
        maximum = EnforcementAction.ALERT
        reason = "Pipeline fallback is ineligible for automatic blocking"
    elif kill_switch:
        maximum = EnforcementAction.ALERT
        reason = "Category/model kill switch prevents automatic blocking"
    elif not block_approved:
        maximum = EnforcementAction.ALERT
        reason = "Exact model, prompt and dataset versions do not have a BLOCK approval"
    else:
        maximum = EnforcementAction.BLOCK
        reason = "Calibrated threshold and exact-version release gate are approved"

    return RiskControlDecision(
        maximum_action=maximum,
        calibrated_confidence=calibrated,
        ambiguous=ambiguous,
        block_gate_approved=block_approved,
        kill_switch_active=kill_switch,
        reason=reason,
    )


def apply_risk_controls(
    policy_decision: PolicyDecision,
    pipeline_result: PipelineResult,
    *,
    versions: VersionSet,
    config: RiskControlConfig,
) -> tuple[PolicyDecision, RiskControlDecision]:
    controls = evaluate_risk_controls(
        pipeline_result.assessment,
        versions=versions,
        config=config,
        pipeline_block_eligible=pipeline_result.eligible_for_automatic_block,
    )
    if ACTION_ORDER[policy_decision.action] <= ACTION_ORDER[controls.maximum_action]:
        return policy_decision, controls
    return (
        policy_decision.model_copy(
            update={
                "action": controls.maximum_action,
                "reason": f"{policy_decision.reason}; {controls.reason}",
            }
        ),
        controls,
    )


def controls_as_pretty_json(config: RiskControlConfig) -> str:
    return json.dumps(config.model_dump(mode="json"), indent=2, ensure_ascii=False) + "\n"
