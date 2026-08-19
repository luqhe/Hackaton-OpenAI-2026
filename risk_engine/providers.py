from __future__ import annotations

from guardian_core.models import Observation, RiskAssessment, RiskLevel
from risk_engine.contracts import ContextBundle, ProviderDescriptor
from risk_engine.engine import EDUCATIONAL_MARKERS, assess_risk

LOCAL_PROMPT_VERSION = "heuristic-rules.v1"
FALLBACK_PROMPT_VERSION = "conservative-fallback.v1"


def _observation_with_ocr(context: ContextBundle) -> Observation:
    visible_parts = [context.observation.visible_text, context.ocr_text]
    return context.observation.model_copy(
        update={"visible_text": "\n".join(part for part in visible_parts if part)}
    )


class HeuristicLocalProvider:
    descriptor = ProviderDescriptor(
        provider="guardian-local",
        provider_version="1.0.0",
        model_version="heuristic-context-v1",
        prompt_version=LOCAL_PROMPT_VERSION,
    )

    def classify(self, context: ContextBundle, *, timeout: float) -> RiskAssessment:
        del timeout
        return assess_risk(_observation_with_ocr(context))

    def trusted_safe_rule(self, context: ContextBundle, assessment: RiskAssessment) -> str | None:
        if assessment.risk != RiskLevel.SAFE or assessment.confidence < 0.9:
            return None
        observation = _observation_with_ocr(context)
        combined = f"{observation.window_title}\n{observation.visible_text}".lower()
        if any(marker in combined for marker in EDUCATIONAL_MARKERS):
            return "EDUCATIONAL_CONTEXT"
        if (
            not combined.strip()
            and not observation.recent_messages
            and not observation.media_detected
            and context.selected_frame_path is None
        ):
            return "EMPTY_TEXT_CONTEXT"
        return None


class ConservativeFallbackProvider:
    descriptor = ProviderDescriptor(
        provider="guardian-fallback",
        provider_version="1.0.0",
        model_version="local-signal-no-block-v1",
        prompt_version=FALLBACK_PROMPT_VERSION,
    )

    def classify_from_local(self, local: RiskAssessment) -> RiskAssessment:
        if local.risk == RiskLevel.SAFE:
            return local.model_copy(
                update={
                    "confidence": min(local.confidence, 0.5),
                    "explanation": (
                        "Remote context analysis was unavailable; no supported local risk signal was found. "
                        "Automatic intervention is disabled for this fallback result."
                    ),
                }
            )
        return local.model_copy(
            update={
                "risk": RiskLevel.MEDIUM,
                "confidence": min(local.confidence, 0.69),
                "explanation": (
                    f"{local.explanation} Remote confirmation was unavailable, so the signal was kept for "
                    "review and made ineligible for automatic blocking."
                ),
            }
        )
