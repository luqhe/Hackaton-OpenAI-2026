from __future__ import annotations

import re

from guardian_core.models import Observation, RiskAssessment, RiskCategory, RiskDirection, RiskLevel


EDUCATIONAL_MARKERS = {
    "biology",
    "biologia",
    "reproduction",
    "reprodução",
    "classroom",
    "aula",
    "textbook",
    "livro didático",
}

CONTACT_SIGNALS: dict[str, tuple[str, ...]] = {
    "age": (r"\bhow old are you\b", r"\bqual (?:é )?a sua idade\b", r"\bquantos anos você tem\b"),
    "school": (r"\bwhat school do you (?:go to|attend)\b", r"\bem que escola você estuda\b"),
    "social": (r"\bsend me your instagram\b", r"\bme passa (?:seu|o seu) instagram\b"),
    "photo": (r"\bsend me (?:a|your) (?:picture|photo)\b", r"\bme manda (?:uma|sua) foto\b"),
    "secret": (r"\bdon't tell your parents\b", r"\bnão conta (?:para|pros?) seus pais\b"),
    "location": (r"\bwhere do you live\b", r"\bonde você mora\b"),
}

ADULT_SIGNALS = (
    r"\bexplicit sexual content\b",
    r"\bporn(?:ography|ográfico|ografia)?\b",
    r"\bnude(?:s|z)?\b",
)

HATE_SIGNALS = (
    r"\b(?:racial|homophobic|transphobic) slur\b",
    r"\bdiscurso de ódio\b",
    r"\b(?:grupo|povo) inferior\b",
)


def _matches(patterns: tuple[str, ...], text: str) -> bool:
    return any(re.search(pattern, text, flags=re.IGNORECASE) for pattern in patterns)


def assess_risk(observation: Observation) -> RiskAssessment:
    messages = "\n".join(f"{message.speaker}: {message.text}" for message in observation.recent_messages)
    combined = f"{observation.window_title}\n{observation.visible_text}\n{messages}".lower()

    if any(marker in combined for marker in EDUCATIONAL_MARKERS):
        return RiskAssessment(
            risk=RiskLevel.SAFE,
            confidence=0.94,
            explanation="Sensitive terminology appears in an educational context.",
        )

    contact_hits = [label for label, patterns in CONTACT_SIGNALS.items() if _matches(patterns, combined)]
    if len(contact_hits) >= 3:
        confidence = min(0.82 + (len(contact_hits) - 3) * 0.04, 0.98)
        return RiskAssessment(
            risk=RiskLevel.HIGH,
            category=RiskCategory.DANGEROUS_CONTACT,
            direction=RiskDirection.CHILD_AS_TARGET,
            confidence=confidence,
            evidence=[f"Progressive request detected: {label}" for label in contact_hits],
            explanation=(
                "The conversation progressively requests age, school, social profile, photos or location. "
                "Together these signals may indicate an unsafe attempt to obtain personal information."
            ),
        )
    if contact_hits:
        return RiskAssessment(
            risk=RiskLevel.MEDIUM,
            category=RiskCategory.DANGEROUS_CONTACT,
            direction=RiskDirection.CHILD_AS_TARGET,
            confidence=min(0.48 + len(contact_hits) * 0.1, 0.72),
            evidence=[f"Personal-information request detected: {label}" for label in contact_hits],
            explanation="The conversation contains an isolated request for personal information; more context is needed.",
        )

    if _matches(ADULT_SIGNALS, combined):
        return RiskAssessment(
            risk=RiskLevel.HIGH,
            category=RiskCategory.ADULT_CONTENT,
            direction=RiskDirection.CONTENT_CONSUMPTION,
            confidence=0.91,
            evidence=["Explicit adult-content signal detected"],
            explanation="The visible content contains strong signals of explicit adult material.",
        )

    if _matches(HATE_SIGNALS, combined):
        return RiskAssessment(
            risk=RiskLevel.HIGH,
            category=RiskCategory.HATE_SPEECH,
            direction=RiskDirection.CHILD_AS_TARGET,
            confidence=0.88,
            evidence=["Discriminatory or dehumanizing language detected"],
            explanation="The visible conversation contains a strong hate-speech signal.",
        )

    return RiskAssessment(
        risk=RiskLevel.SAFE,
        confidence=0.9,
        explanation="No supported high-risk pattern was found in the recent context.",
    )
