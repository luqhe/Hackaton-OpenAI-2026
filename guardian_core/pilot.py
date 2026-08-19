from __future__ import annotations

from enum import StrEnum
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, model_validator

from guardian_core.models import EnforcementAction, PolicyDecision, RiskCategory
from risk_engine.calibration import RiskControlDecision, VersionSet


class PilotMode(StrEnum):
    TECHNICAL_SHADOW = "TECHNICAL_SHADOW"
    ALERT_ONLY = "ALERT_ONLY"
    LIMITED_BLOCK = "LIMITED_BLOCK"


TECHNICAL_TELEMETRY_FIELDS = frozenset(
    {
        "agent_version",
        "api_latency_ms",
        "battery_impact_percent",
        "command_latency_ms",
        "cpu_percent",
        "memory_mb",
        "offline_queue_depth",
        "permission_state",
    }
)


class PilotRolloutConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: str = "guardian.pilot-rollout.v1"
    rollout_id: str = Field(min_length=1, max_length=120)
    mode: PilotMode
    cohort_ids: frozenset[str] = Field(min_length=1)
    technical_telemetry_fields: frozenset[str] = TECHNICAL_TELEMETRY_FIELDS
    alert_approvals: tuple[AlertApproval, ...] = ()
    block_approvals: tuple[BlockPilotApproval, ...] = ()
    kill_switches: tuple[PilotKillSwitch, ...] = ()

    @model_validator(mode="after")
    def validate_technical_telemetry(self) -> PilotRolloutConfig:
        unsupported = self.technical_telemetry_fields - TECHNICAL_TELEMETRY_FIELDS
        if unsupported:
            raise ValueError(f"Pilot telemetry includes unsupported fields: {sorted(unsupported)}")
        return self


class AlertApproval(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    approval_id: str = Field(min_length=1, max_length=120)
    category: RiskCategory
    cohort_ids: frozenset[str] = Field(min_length=1)
    versions: VersionSet
    shadow_window_id: str = Field(min_length=1, max_length=120)
    eval_gate_passed: bool
    shadow_gate_passed: bool
    product_safety_approved: bool
    engineering_approved: bool

    @property
    def approved(self) -> bool:
        return all(
            (
                self.eval_gate_passed,
                self.shadow_gate_passed,
                self.product_safety_approved,
                self.engineering_approved,
            )
        )


class BlockPilotApproval(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    approval_id: str = Field(min_length=1, max_length=120)
    category: RiskCategory
    cohort_ids: frozenset[str] = Field(min_length=1)
    versions: VersionSet
    shadow_window_id: str = Field(min_length=1, max_length=120)
    alert_pilot_window_id: str = Field(min_length=1, max_length=120)
    eval_gate_passed: bool
    shadow_gate_passed: bool
    alert_pilot_gate_passed: bool
    product_safety_approved: bool
    engineering_approved: bool
    rollback_tested: bool

    @property
    def approved(self) -> bool:
        return all(
            (
                self.eval_gate_passed,
                self.shadow_gate_passed,
                self.alert_pilot_gate_passed,
                self.product_safety_approved,
                self.engineering_approved,
                self.rollback_tested,
            )
        )


class PilotKillSwitch(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    switch_id: str = Field(min_length=1, max_length=120)
    enabled: bool = True
    category: RiskCategory | None = None
    cohort_id: str | None = Field(default=None, min_length=1, max_length=120)
    ceiling: EnforcementAction = EnforcementAction.LOG
    reason: str = Field(min_length=1, max_length=500)

    @model_validator(mode="after")
    def validate_ceiling(self) -> PilotKillSwitch:
        if self.ceiling not in {EnforcementAction.LOG, EnforcementAction.ALERT}:
            raise ValueError("A pilot kill switch ceiling must be LOG or ALERT")
        return self


class PilotActionDecision(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    rollout_id: str
    mode: PilotMode
    proposed_action: EnforcementAction
    effective_action: EnforcementAction
    simulated_action: EnforcementAction
    actual_intervention: bool
    approval_id: str | None = None
    kill_switch_id: str | None = None
    reason: str


def load_pilot_rollout(path: Path) -> PilotRolloutConfig:
    return PilotRolloutConfig.model_validate_json(path.read_text(encoding="utf-8"))


def fail_safe_pilot_rollout() -> PilotRolloutConfig:
    """Built-in state used when no trustworthy rollout configuration is available."""
    return PilotRolloutConfig(
        rollout_id="runtime-fail-safe",
        mode=PilotMode.TECHNICAL_SHADOW,
        cohort_ids=frozenset({"__fail_safe__"}),
        kill_switches=(
            PilotKillSwitch(
                switch_id="runtime-fail-safe",
                ceiling=EnforcementAction.LOG,
                reason="No validated pilot rollout configuration is available",
            ),
        ),
    )


def _matching_alert_approval(
    config: PilotRolloutConfig,
    *,
    category: RiskCategory | None,
    cohort_id: str,
    versions: VersionSet,
) -> AlertApproval | None:
    if category is None:
        return None
    return next(
        (
            approval
            for approval in config.alert_approvals
            if approval.approved
            and approval.category == category
            and cohort_id in approval.cohort_ids
            and approval.versions == versions
        ),
        None,
    )


def _matching_block_approval(
    config: PilotRolloutConfig,
    *,
    category: RiskCategory | None,
    cohort_id: str,
    versions: VersionSet,
) -> BlockPilotApproval | None:
    if category is None:
        return None
    return next(
        (
            approval
            for approval in config.block_approvals
            if approval.approved
            and approval.category == category
            and cohort_id in approval.cohort_ids
            and approval.versions == versions
        ),
        None,
    )


PILOT_ACTION_ORDER = {
    EnforcementAction.IGNORE: 0,
    EnforcementAction.LOG: 1,
    EnforcementAction.ALERT: 2,
    EnforcementAction.BLOCK: 3,
}


def _active_kill_switch(
    config: PilotRolloutConfig,
    *,
    category: RiskCategory | None,
    cohort_id: str,
) -> PilotKillSwitch | None:
    matches = [
        switch
        for switch in config.kill_switches
        if switch.enabled
        and (switch.category is None or switch.category == category)
        and (switch.cohort_id is None or switch.cohort_id == cohort_id)
    ]
    return min(matches, key=lambda item: PILOT_ACTION_ORDER[item.ceiling], default=None)


def apply_pilot_rollout(
    decision: PolicyDecision,
    *,
    category: RiskCategory | None,
    cohort_id: str,
    versions: VersionSet,
    config: PilotRolloutConfig,
    risk_control_decision: RiskControlDecision | None = None,
) -> tuple[PolicyDecision, PilotActionDecision]:
    """Apply the last, fail-safe rollout gate before an action reaches the device."""
    approval: AlertApproval | None = None
    if cohort_id not in config.cohort_ids:
        effective = EnforcementAction.LOG if decision.action != EnforcementAction.IGNORE else decision.action
        reason = "Cohort is outside the active pilot rollout"
    elif config.mode == PilotMode.TECHNICAL_SHADOW:
        effective = EnforcementAction.LOG if decision.action != EnforcementAction.IGNORE else decision.action
        reason = "Technical shadow mode records the proposal without a real intervention"
    elif config.mode == PilotMode.ALERT_ONLY:
        approval = _matching_alert_approval(
            config,
            category=category,
            cohort_id=cohort_id,
            versions=versions,
        )
        if decision.action in {EnforcementAction.IGNORE, EnforcementAction.LOG}:
            effective = decision.action
            reason = "Non-intervention action is within the alert-only ceiling"
        elif approval is None:
            effective = EnforcementAction.LOG
            reason = "Category, cohort and exact versions lack an approved alert gate"
        else:
            effective = EnforcementAction.ALERT
            reason = "Approved category, cohort and exact versions permit ALERT but never BLOCK"
    else:
        alert_approval = _matching_alert_approval(
            config,
            category=category,
            cohort_id=cohort_id,
            versions=versions,
        )
        block_approval = _matching_block_approval(
            config,
            category=category,
            cohort_id=cohort_id,
            versions=versions,
        )
        if decision.action in {EnforcementAction.IGNORE, EnforcementAction.LOG}:
            effective = decision.action
            reason = "Non-intervention action is within the limited-block ceiling"
        elif decision.action == EnforcementAction.ALERT:
            effective = EnforcementAction.ALERT if alert_approval else EnforcementAction.LOG
            approval = alert_approval
            reason = (
                "Exact pilot alert approval permits ALERT"
                if alert_approval
                else "Category, cohort and exact versions lack an approved alert gate"
            )
        else:
            upstream_allows_block = (
                risk_control_decision is not None
                and risk_control_decision.maximum_action == EnforcementAction.BLOCK
                and risk_control_decision.block_gate_approved
                and not risk_control_decision.kill_switch_active
            )
            if block_approval and upstream_allows_block:
                effective = EnforcementAction.BLOCK
                approval = block_approval
                reason = "Exact R3 and pilot category/cohort gates permit limited BLOCK"
            else:
                effective = EnforcementAction.ALERT if alert_approval else EnforcementAction.LOG
                approval = alert_approval
                reason = (
                    "BLOCK gate failed; exact alert approval limits the action to ALERT"
                    if alert_approval
                    else "BLOCK gate failed and no exact alert approval exists"
                )

    kill_switch = _active_kill_switch(config, category=category, cohort_id=cohort_id)
    if kill_switch and PILOT_ACTION_ORDER[effective] > PILOT_ACTION_ORDER[kill_switch.ceiling]:
        effective = kill_switch.ceiling
        reason = f"{reason}; pilot kill switch {kill_switch.switch_id} applies: {kill_switch.reason}"

    gated = decision
    if effective != decision.action:
        gated = decision.model_copy(
            update={
                "action": effective,
                "reason": f"{decision.reason}; {reason}",
            }
        )
    pilot_decision = PilotActionDecision(
        rollout_id=config.rollout_id,
        mode=config.mode,
        proposed_action=decision.action,
        effective_action=effective,
        simulated_action=decision.action,
        actual_intervention=effective in {EnforcementAction.ALERT, EnforcementAction.BLOCK},
        approval_id=approval.approval_id if approval else None,
        kill_switch_id=kill_switch.switch_id if kill_switch else None,
        reason=reason,
    )
    return gated, pilot_decision
