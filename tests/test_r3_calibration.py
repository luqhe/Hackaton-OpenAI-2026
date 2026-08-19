from __future__ import annotations

from pathlib import Path

from guardian_core.models import (
    EnforcementAction,
    PolicyDecision,
    RiskAssessment,
    RiskCategory,
    RiskDirection,
    RiskLevel,
)
from risk_engine.calibration import (
    BlockApproval,
    VersionSet,
    apply_risk_controls,
    evaluate_risk_controls,
    load_controls,
)
from risk_engine.pipeline import AnalysisSource, PipelineResult

ROOT = Path(__file__).resolve().parents[1]
CONTROL_PATH = ROOT / "config" / "risk-controls.v1.json"
VERSIONS = VersionSet(
    model="fake-model-v1",
    prompt="prompt-v1",
    dataset="dataset-v1",
)


def assessment(confidence: float = 0.99) -> RiskAssessment:
    return RiskAssessment(
        risk=RiskLevel.HIGH,
        category=RiskCategory.DANGEROUS_CONTACT,
        direction=RiskDirection.CHILD_AS_TARGET,
        confidence=confidence,
        evidence=["signal"],
        explanation="High-risk progressive contact.",
    )


def pipeline_result(*, block_eligible: bool = True) -> PipelineResult:
    result = assessment()
    return PipelineResult(
        assessment=result,
        local_assessment=result,
        source=AnalysisSource.REMOTE,
        context_digest="0" * 64,
        provider_version="1",
        model_version=VERSIONS.model,
        prompt_version=VERSIONS.prompt,
        remote_attempted=True,
        attempts=1,
        eligible_for_automatic_block=block_eligible,
    )


def approved_config():
    config = load_controls(CONTROL_PATH)
    approval = BlockApproval(
        category=RiskCategory.DANGEROUS_CONTACT,
        versions=VERSIONS,
        shadow_window_id="staging-window-42",
        shadow_gate_passed=True,
        product_safety_approved=True,
        engineering_approved=True,
    )
    return config.model_copy(update={"kill_switches": (), "block_approvals": (approval,)})


def test_config_has_distinct_thresholds_and_category_calibration() -> None:
    config = load_controls(CONTROL_PATH)
    for category in RiskCategory:
        controls = config.category(category)
        assert controls.log_threshold < controls.alert_threshold < controls.block_threshold
        assert len(controls.calibration) >= 2


def test_kill_switch_prevents_block_even_at_high_confidence() -> None:
    decision = evaluate_risk_controls(
        assessment(),
        versions=VERSIONS,
        config=load_controls(CONTROL_PATH),
        pipeline_block_eligible=True,
    )

    assert decision.maximum_action == EnforcementAction.ALERT
    assert decision.kill_switch_active is True


def test_exact_approved_versions_can_pass_block_gate() -> None:
    decision = evaluate_risk_controls(
        assessment(),
        versions=VERSIONS,
        config=approved_config(),
        pipeline_block_eligible=True,
    )

    assert decision.maximum_action == EnforcementAction.BLOCK
    assert decision.block_gate_approved is True


def test_model_or_prompt_update_invalidates_previous_block_approval() -> None:
    updated = VERSIONS.model_copy(update={"prompt": "prompt-v2"})
    decision = evaluate_risk_controls(
        assessment(),
        versions=updated,
        config=approved_config(),
        pipeline_block_eligible=True,
    )

    assert decision.maximum_action == EnforcementAction.ALERT
    assert decision.block_gate_approved is False


def test_fallback_and_ambiguous_zone_never_auto_block() -> None:
    policy = PolicyDecision(action=EnforcementAction.BLOCK, reason="Parent selected BLOCK")
    gated, controls = apply_risk_controls(
        policy,
        pipeline_result(block_eligible=False),
        versions=VERSIONS,
        config=approved_config(),
    )

    assert gated.action == EnforcementAction.ALERT
    assert controls.maximum_action == EnforcementAction.ALERT

    ambiguous = evaluate_risk_controls(
        assessment(confidence=0.82),
        versions=VERSIONS,
        config=approved_config(),
        pipeline_block_eligible=True,
    )
    assert ambiguous.ambiguous is True
    assert ambiguous.maximum_action != EnforcementAction.BLOCK
