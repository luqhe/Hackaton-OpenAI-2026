import json
from pathlib import Path

from guardian_core.models import Observation, PolicyAction, PolicyRule, RiskCategory, RiskLevel
from guardian_core.policy import apply_policy
from risk_engine import assess_risk


ROOT = Path(__file__).resolve().parents[1]


def observation_from_fixture(name: str) -> Observation:
    payload = json.loads((ROOT / "fixtures" / name / "session.json").read_text(encoding="utf-8"))
    return Observation(
        app_name=payload["app_name"],
        window_title=payload.get("window_title", ""),
        visible_text=payload.get("visible_text", ""),
        recent_messages=payload.get("messages", []),
    )


def test_dangerous_contact_uses_temporal_context() -> None:
    result = assess_risk(observation_from_fixture("dangerous_contact"))
    assert result.risk == RiskLevel.HIGH
    assert result.category == RiskCategory.DANGEROUS_CONTACT
    assert result.confidence >= 0.82
    assert len(result.evidence) >= 3


def test_educational_context_avoids_keyword_false_positive() -> None:
    result = assess_risk(observation_from_fixture("safe_biology"))
    assert result.risk == RiskLevel.SAFE
    assert result.category is None
    assert result.direction is None


def test_policy_engine_owns_the_block_decision() -> None:
    assessment = assess_risk(observation_from_fixture("dangerous_contact"))
    decision = apply_policy(
        assessment,
        [
            PolicyRule(
                category=RiskCategory.DANGEROUS_CONTACT,
                action=PolicyAction.BLOCK,
                minimum_risk=RiskLevel.HIGH,
                minimum_confidence=0.75,
            )
        ],
    )
    assert decision.action == "BLOCK"
    assert "action" not in assessment.model_dump()

