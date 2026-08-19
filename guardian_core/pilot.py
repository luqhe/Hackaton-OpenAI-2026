from __future__ import annotations

from enum import StrEnum
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, model_validator

from guardian_core.models import EnforcementAction, PolicyDecision, RiskCategory
from risk_engine.calibration import VersionSet


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

    @model_validator(mode="after")
    def validate_technical_telemetry(self) -> PilotRolloutConfig:
        unsupported = self.technical_telemetry_fields - TECHNICAL_TELEMETRY_FIELDS
        if unsupported:
            raise ValueError(f"Pilot telemetry includes unsupported fields: {sorted(unsupported)}")
        return self


class PilotActionDecision(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    rollout_id: str
    mode: PilotMode
    proposed_action: EnforcementAction
    effective_action: EnforcementAction
    simulated_action: EnforcementAction
    actual_intervention: bool
    reason: str


def load_pilot_rollout(path: Path) -> PilotRolloutConfig:
    return PilotRolloutConfig.model_validate_json(path.read_text(encoding="utf-8"))


def apply_pilot_rollout(
    decision: PolicyDecision,
    *,
    category: RiskCategory | None,
    cohort_id: str,
    versions: VersionSet,
    config: PilotRolloutConfig,
) -> tuple[PolicyDecision, PilotActionDecision]:
    """Apply the last, fail-safe rollout gate before an action reaches the device."""
    del category, versions  # Used by category/version approvals in later rollout modes.
    if cohort_id not in config.cohort_ids:
        effective = EnforcementAction.LOG if decision.action != EnforcementAction.IGNORE else decision.action
        reason = "Cohort is outside the active pilot rollout"
    elif config.mode == PilotMode.TECHNICAL_SHADOW:
        effective = EnforcementAction.LOG if decision.action != EnforcementAction.IGNORE else decision.action
        reason = "Technical shadow mode records the proposal without a real intervention"
    else:
        effective = decision.action
        reason = "Pilot rollout mode allows the proposed action"

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
        reason=reason,
    )
    return gated, pilot_decision
