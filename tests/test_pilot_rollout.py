from pathlib import Path

import pytest
from pydantic import ValidationError

from guardian_core.models import EnforcementAction, PolicyDecision, RiskCategory
from guardian_core.pilot import (
    TECHNICAL_TELEMETRY_FIELDS,
    AlertApproval,
    BlockPilotApproval,
    PilotKillSwitch,
    PilotMode,
    PilotRolloutConfig,
    apply_pilot_rollout,
    load_pilot_rollout,
)
from risk_engine.calibration import RiskControlDecision, VersionSet

ROOT = Path(__file__).resolve().parents[1]
PILOT_CONFIG_PATH = ROOT / "config" / "pilot-rollout.v1.json"
VERSIONS = VersionSet(model="model-v1", prompt="prompt-v1", dataset="dataset-v1")


def proposed_block() -> PolicyDecision:
    return PolicyDecision(action=EnforcementAction.BLOCK, reason="Policy and risk gates proposed BLOCK")


def alert_only_config() -> PilotRolloutConfig:
    config = load_pilot_rollout(PILOT_CONFIG_PATH)
    approval = AlertApproval(
        approval_id="alert-dangerous-contact-v1",
        category=RiskCategory.DANGEROUS_CONTACT,
        cohort_ids=frozenset({"pilot-alert-a"}),
        versions=VERSIONS,
        shadow_window_id="staging-dangerous-contact-01",
        eval_gate_passed=True,
        shadow_gate_passed=True,
        product_safety_approved=True,
        engineering_approved=True,
    )
    return config.model_copy(
        update={
            "mode": PilotMode.ALERT_ONLY,
            "cohort_ids": frozenset({"pilot-alert-a"}),
            "alert_approvals": (approval,),
            "kill_switches": (),
        }
    )


def block_control_decision(
    *,
    maximum_action: EnforcementAction = EnforcementAction.BLOCK,
    kill_switch_active: bool = False,
) -> RiskControlDecision:
    return RiskControlDecision(
        maximum_action=maximum_action,
        calibrated_confidence=0.98,
        ambiguous=False,
        block_gate_approved=True,
        kill_switch_active=kill_switch_active,
        reason="R3 gate result",
    )


def limited_block_config() -> PilotRolloutConfig:
    alert_config = alert_only_config()
    approval = BlockPilotApproval(
        approval_id="block-dangerous-contact-cohort-a-v1",
        category=RiskCategory.DANGEROUS_CONTACT,
        cohort_ids=frozenset({"pilot-alert-a"}),
        versions=VERSIONS,
        shadow_window_id="staging-dangerous-contact-01",
        alert_pilot_window_id="pilot-alert-dangerous-contact-01",
        eval_gate_passed=True,
        shadow_gate_passed=True,
        alert_pilot_gate_passed=True,
        product_safety_approved=True,
        engineering_approved=True,
        rollback_tested=True,
    )
    return alert_config.model_copy(
        update={
            "mode": PilotMode.LIMITED_BLOCK,
            "block_approvals": (approval,),
        }
    )


def test_technical_shadow_never_intervenes() -> None:
    config = load_pilot_rollout(PILOT_CONFIG_PATH)

    gated, audit = apply_pilot_rollout(
        proposed_block(),
        category=RiskCategory.DANGEROUS_CONTACT,
        cohort_id="pilot-technical",
        versions=VERSIONS,
        config=config,
    )

    assert gated.action == EnforcementAction.LOG
    assert audit.simulated_action == EnforcementAction.BLOCK
    assert audit.actual_intervention is False
    assert config.technical_telemetry_fields == TECHNICAL_TELEMETRY_FIELDS


def test_unknown_cohort_fails_to_log_only() -> None:
    gated, audit = apply_pilot_rollout(
        PolicyDecision(action=EnforcementAction.ALERT, reason="Policy proposed ALERT"),
        category=RiskCategory.ADULT_CONTENT,
        cohort_id="not-enrolled",
        versions=VERSIONS,
        config=load_pilot_rollout(PILOT_CONFIG_PATH),
    )

    assert gated.action == EnforcementAction.LOG
    assert audit.actual_intervention is False
    assert "outside" in audit.reason


def test_pilot_config_rejects_content_telemetry() -> None:
    raw = load_pilot_rollout(PILOT_CONFIG_PATH).model_dump(mode="json")
    raw["technical_telemetry_fields"].append("visible_text")

    with pytest.raises(ValidationError, match="unsupported fields"):
        PilotRolloutConfig.model_validate(raw)


def test_alert_only_caps_approved_block_proposal_at_alert() -> None:
    gated, audit = apply_pilot_rollout(
        proposed_block(),
        category=RiskCategory.DANGEROUS_CONTACT,
        cohort_id="pilot-alert-a",
        versions=VERSIONS,
        config=alert_only_config(),
    )

    assert gated.action == EnforcementAction.ALERT
    assert audit.proposed_action == EnforcementAction.BLOCK
    assert audit.approval_id == "alert-dangerous-contact-v1"


@pytest.mark.parametrize(
    ("category", "cohort_id", "versions"),
    [
        (RiskCategory.ADULT_CONTENT, "pilot-alert-a", VERSIONS),
        (RiskCategory.DANGEROUS_CONTACT, "not-approved", VERSIONS),
        (
            RiskCategory.DANGEROUS_CONTACT,
            "pilot-alert-a",
            VERSIONS.model_copy(update={"prompt": "prompt-v2"}),
        ),
    ],
)
def test_alert_only_requires_exact_approved_category_cohort_and_versions(
    category: RiskCategory,
    cohort_id: str,
    versions: VersionSet,
) -> None:
    gated, audit = apply_pilot_rollout(
        PolicyDecision(action=EnforcementAction.ALERT, reason="Policy proposed ALERT"),
        category=category,
        cohort_id=cohort_id,
        versions=versions,
        config=alert_only_config(),
    )

    assert gated.action == EnforcementAction.LOG
    assert audit.approval_id is None


def test_limited_block_requires_exact_pilot_and_upstream_gates() -> None:
    gated, audit = apply_pilot_rollout(
        proposed_block(),
        category=RiskCategory.DANGEROUS_CONTACT,
        cohort_id="pilot-alert-a",
        versions=VERSIONS,
        config=limited_block_config(),
        risk_control_decision=block_control_decision(),
    )

    assert gated.action == EnforcementAction.BLOCK
    assert audit.approval_id == "block-dangerous-contact-cohort-a-v1"


@pytest.mark.parametrize(
    "risk_control_decision",
    [
        None,
        block_control_decision(maximum_action=EnforcementAction.ALERT),
        block_control_decision(kill_switch_active=True),
    ],
)
def test_limited_block_falls_back_to_approved_alert_when_upstream_gate_fails(
    risk_control_decision: RiskControlDecision | None,
) -> None:
    gated, audit = apply_pilot_rollout(
        proposed_block(),
        category=RiskCategory.DANGEROUS_CONTACT,
        cohort_id="pilot-alert-a",
        versions=VERSIONS,
        config=limited_block_config(),
        risk_control_decision=risk_control_decision,
    )

    assert gated.action == EnforcementAction.ALERT
    assert audit.approval_id == "alert-dangerous-contact-v1"


def test_limited_block_fails_to_log_on_version_mismatch() -> None:
    gated, audit = apply_pilot_rollout(
        proposed_block(),
        category=RiskCategory.DANGEROUS_CONTACT,
        cohort_id="pilot-alert-a",
        versions=VERSIONS.model_copy(update={"model": "model-v2"}),
        config=limited_block_config(),
        risk_control_decision=block_control_decision(),
    )

    assert gated.action == EnforcementAction.LOG
    assert audit.approval_id is None


def test_global_kill_switch_overrides_every_block_approval() -> None:
    config = limited_block_config().model_copy(
        update={
            "kill_switches": (
                PilotKillSwitch(
                    switch_id="global-stop",
                    ceiling=EnforcementAction.LOG,
                    reason="Pilot paused by incident commander",
                ),
            )
        }
    )
    gated, audit = apply_pilot_rollout(
        proposed_block(),
        category=RiskCategory.DANGEROUS_CONTACT,
        cohort_id="pilot-alert-a",
        versions=VERSIONS,
        config=config,
        risk_control_decision=block_control_decision(),
    )

    assert gated.action == EnforcementAction.LOG
    assert audit.kill_switch_id == "global-stop"
    assert audit.actual_intervention is False


def test_category_and_cohort_kill_switch_is_granular() -> None:
    switch = PilotKillSwitch(
        switch_id="dangerous-contact-cohort-a-stop",
        category=RiskCategory.DANGEROUS_CONTACT,
        cohort_id="pilot-alert-a",
        ceiling=EnforcementAction.ALERT,
        reason="Category investigation",
    )
    config = limited_block_config().model_copy(update={"kill_switches": (switch,)})
    gated, audit = apply_pilot_rollout(
        proposed_block(),
        category=RiskCategory.DANGEROUS_CONTACT,
        cohort_id="pilot-alert-a",
        versions=VERSIONS,
        config=config,
        risk_control_decision=block_control_decision(),
    )

    assert gated.action == EnforcementAction.ALERT
    assert audit.kill_switch_id == switch.switch_id

    unaffected_config = config.model_copy(update={"cohort_ids": frozenset({"pilot-alert-b"})})
    unaffected_approval = config.block_approvals[0].model_copy(
        update={"cohort_ids": frozenset({"pilot-alert-b"})}
    )
    unaffected_alert = config.alert_approvals[0].model_copy(
        update={"cohort_ids": frozenset({"pilot-alert-b"})}
    )
    unaffected_config = unaffected_config.model_copy(
        update={
            "block_approvals": (unaffected_approval,),
            "alert_approvals": (unaffected_alert,),
        }
    )
    unaffected, audit = apply_pilot_rollout(
        proposed_block(),
        category=RiskCategory.DANGEROUS_CONTACT,
        cohort_id="pilot-alert-b",
        versions=VERSIONS,
        config=unaffected_config,
        risk_control_decision=block_control_decision(),
    )
    assert unaffected.action == EnforcementAction.BLOCK
    assert audit.kill_switch_id is None
