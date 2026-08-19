from __future__ import annotations

from guardian_core.models import (
    EnforcementAction,
    PolicyAction,
    PolicyDecision,
    PolicyRule,
    RiskAssessment,
    RiskLevel,
)


RISK_ORDER = {
    RiskLevel.SAFE: 0,
    RiskLevel.LOW: 1,
    RiskLevel.MEDIUM: 2,
    RiskLevel.HIGH: 3,
}


def apply_policy(assessment: RiskAssessment, rules: list[PolicyRule]) -> PolicyDecision:
    if assessment.risk == RiskLevel.SAFE or assessment.category is None:
        return PolicyDecision(action=EnforcementAction.IGNORE, reason="No risk requiring policy evaluation")

    rule = next((item for item in rules if item.category == assessment.category), None)
    if rule is None:
        return PolicyDecision(action=EnforcementAction.LOG, reason="No matching parental policy; event logged")

    if RISK_ORDER[assessment.risk] < RISK_ORDER[rule.minimum_risk]:
        return PolicyDecision(
            action=EnforcementAction.LOG,
            matched_rule=rule,
            reason=f"Risk {assessment.risk} is below the configured threshold {rule.minimum_risk}",
        )

    if assessment.confidence < rule.minimum_confidence:
        return PolicyDecision(
            action=EnforcementAction.LOG,
            matched_rule=rule,
            reason="Confidence is below the configured threshold",
        )

    action = {
        PolicyAction.ALLOW: EnforcementAction.IGNORE,
        PolicyAction.ALERT: EnforcementAction.LOG,
        PolicyAction.BLOCK: EnforcementAction.BLOCK,
    }[rule.action]
    return PolicyDecision(action=action, matched_rule=rule, reason="Parental policy matched")

