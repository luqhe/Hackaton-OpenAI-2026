from pathlib import Path

from guardian_core.config import GuardianSettings
from guardian_core.gates import apply_runtime_release_gate
from guardian_core.models import (
    EnforcementAction,
    PolicyAction,
    PolicyDecision,
    PolicyRule,
    RiskCategory,
)


def settings(environment: str, *, automatic_blocking: bool, release_gate: bool) -> GuardianSettings:
    return GuardianSettings.from_env(
        {
            "GUARDIAN_ENVIRONMENT": environment,
            "GUARDIAN_API_URL": "http://testserver",
            "GUARDIAN_DB_PATH": str(Path(".test-runtime") / "gate.db"),
            "GUARDIAN_EVIDENCE_DIR": str(Path(".test-runtime") / "evidence"),
            "GUARDIAN_AUTOMATIC_BLOCKING_ENABLED": str(automatic_blocking).lower(),
            "GUARDIAN_REAL_ENFORCEMENT_ENABLED": "false",
            "GUARDIAN_RELEASE_GATE_APPROVED": str(release_gate).lower(),
        }
    )


def block_decision() -> PolicyDecision:
    return PolicyDecision(
        action=EnforcementAction.BLOCK,
        matched_rule=PolicyRule(category=RiskCategory.DANGEROUS_CONTACT, action=PolicyAction.BLOCK),
        reason="Parental policy matched",
    )


def test_fixture_block_is_allowed_only_in_local_demo_environment() -> None:
    decision = apply_runtime_release_gate(
        block_decision(),
        settings("test", automatic_blocking=True, release_gate=False),
        fixture_input=True,
    )
    assert decision.action == EnforcementAction.BLOCK


def test_nonlocal_block_is_downgraded_without_approved_gate() -> None:
    decision = apply_runtime_release_gate(
        block_decision(),
        settings("staging", automatic_blocking=False, release_gate=False),
        fixture_input=False,
    )
    assert decision.action == EnforcementAction.ALERT
    assert "runtime release gate" in decision.reason


def test_approved_nonlocal_gate_can_preserve_block() -> None:
    decision = apply_runtime_release_gate(
        block_decision(),
        settings("production", automatic_blocking=True, release_gate=True),
        fixture_input=False,
    )
    assert decision.action == EnforcementAction.BLOCK


def test_parent_alert_policy_produces_alert_not_log() -> None:
    alert = PolicyDecision(action=EnforcementAction.ALERT, reason="Parental policy matched")
    gated = apply_runtime_release_gate(
        alert,
        settings("staging", automatic_blocking=False, release_gate=False),
        fixture_input=False,
    )
    assert gated.action == EnforcementAction.ALERT
