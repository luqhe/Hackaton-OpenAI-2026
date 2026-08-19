from __future__ import annotations

from guardian_core.config import Environment, GuardianSettings
from guardian_core.models import EnforcementAction, PolicyDecision


def apply_runtime_release_gate(
    decision: PolicyDecision,
    settings: GuardianSettings,
    *,
    fixture_input: bool,
) -> PolicyDecision:
    """Downgrade BLOCK unless the current environment has an explicit safe gate."""
    if decision.action != EnforcementAction.BLOCK:
        return decision

    demo_block_allowed = (
        fixture_input
        and settings.environment in {Environment.DEVELOPMENT, Environment.TEST}
        and settings.automatic_blocking_enabled
    )
    released_block_allowed = settings.automatic_blocking_enabled and settings.release_gate_approved
    if demo_block_allowed or released_block_allowed:
        return decision

    return decision.model_copy(
        update={
            "action": EnforcementAction.ALERT,
            "reason": f"{decision.reason}; downgraded to ALERT by the runtime release gate",
        }
    )
