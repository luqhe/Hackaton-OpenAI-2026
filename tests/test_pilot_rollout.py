from pathlib import Path

import pytest
from pydantic import ValidationError

from guardian_core.models import EnforcementAction, PolicyDecision, RiskCategory
from guardian_core.pilot import (
    TECHNICAL_TELEMETRY_FIELDS,
    AlertApproval,
    PilotMode,
    PilotRolloutConfig,
    apply_pilot_rollout,
    load_pilot_rollout,
)
from risk_engine.calibration import VersionSet

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
