from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, model_validator

from guardian_core.models import RiskCategory


class ClassificationOutcome(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    event_id: str = Field(min_length=1, max_length=120)
    cohort_id: str = Field(min_length=1, max_length=120)
    category: RiskCategory
    model_flagged: bool
    human_reviewed: bool
    human_confirmed_risk: bool | None = None
    incident_shown: bool
    contested: bool = False

    @model_validator(mode="after")
    def validate_outcome(self) -> ClassificationOutcome:
        if self.human_confirmed_risk is not None and not self.human_reviewed:
            raise ValueError("A human outcome requires human_reviewed=true")
        if self.human_reviewed and self.human_confirmed_risk is None:
            raise ValueError("A reviewed outcome requires human_confirmed_risk")
        if self.contested and not self.incident_shown:
            raise ValueError("A contestation requires incident_shown=true")
        return self


class FamilyPilotSurvey(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    response_id: str = Field(min_length=1, max_length=120)
    cohort_id: str = Field(min_length=1, max_length=120)
    family_subject_digest: str = Field(pattern=r"^[a-f0-9]{64}$")
    submitted_at: datetime
    intervention_comprehension: int = Field(ge=1, le=5)
    guardian_confidence: int = Field(ge=1, le=5)


class PilotMetricsSummary(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: str = "guardian.pilot-metrics.v1"
    cohort_id: str
    classification_events: int
    reviewed_flagged_events: int
    false_positives: int
    false_positive_rate: float = Field(ge=0, le=1)
    incidents_shown: int
    contested_incidents: int
    contestation_rate: float = Field(ge=0, le=1)
    survey_responses: int
    intervention_comprehension_mean: float | None = Field(default=None, ge=1, le=5)
    guardian_confidence_mean: float | None = Field(default=None, ge=1, le=5)
    feedback_suppressed: bool
    by_category: dict[str, dict[str, float | int]]


def _category_metrics(records: list[ClassificationOutcome]) -> dict[str, dict[str, float | int]]:
    result: dict[str, dict[str, float | int]] = {}
    for category in sorted({record.category for record in records}, key=lambda item: item.value):
        category_records = [record for record in records if record.category == category]
        reviewed_flagged = [
            record for record in category_records if record.model_flagged and record.human_reviewed
        ]
        false_positives = sum(record.human_confirmed_risk is False for record in reviewed_flagged)
        shown = [record for record in category_records if record.incident_shown]
        contested = sum(record.contested for record in shown)
        result[category.value] = {
            "events": len(category_records),
            "reviewed_flagged_events": len(reviewed_flagged),
            "false_positives": false_positives,
            "false_positive_rate": false_positives / len(reviewed_flagged) if reviewed_flagged else 0.0,
            "incidents_shown": len(shown),
            "contested_incidents": contested,
            "contestation_rate": contested / len(shown) if shown else 0.0,
        }
    return result


def summarize_pilot_metrics(
    cohort_id: str,
    outcomes: list[ClassificationOutcome],
    surveys: list[FamilyPilotSurvey],
    *,
    minimum_feedback_sample: int = 5,
) -> PilotMetricsSummary:
    if minimum_feedback_sample < 2:
        raise ValueError("minimum_feedback_sample must be at least 2")
    cohort_outcomes = [record for record in outcomes if record.cohort_id == cohort_id]
    cohort_surveys = [survey for survey in surveys if survey.cohort_id == cohort_id]
    reviewed_flagged = [
        record for record in cohort_outcomes if record.model_flagged and record.human_reviewed
    ]
    false_positives = sum(record.human_confirmed_risk is False for record in reviewed_flagged)
    shown = [record for record in cohort_outcomes if record.incident_shown]
    contested = sum(record.contested for record in shown)
    feedback_suppressed = len(cohort_surveys) < minimum_feedback_sample
    comprehension = None
    confidence = None
    if not feedback_suppressed:
        comprehension = sum(item.intervention_comprehension for item in cohort_surveys) / len(cohort_surveys)
        confidence = sum(item.guardian_confidence for item in cohort_surveys) / len(cohort_surveys)

    return PilotMetricsSummary(
        cohort_id=cohort_id,
        classification_events=len(cohort_outcomes),
        reviewed_flagged_events=len(reviewed_flagged),
        false_positives=false_positives,
        false_positive_rate=false_positives / len(reviewed_flagged) if reviewed_flagged else 0.0,
        incidents_shown=len(shown),
        contested_incidents=contested,
        contestation_rate=contested / len(shown) if shown else 0.0,
        survey_responses=len(cohort_surveys),
        intervention_comprehension_mean=comprehension,
        guardian_confidence_mean=confidence,
        feedback_suppressed=feedback_suppressed,
        by_category=_category_metrics(cohort_outcomes),
    )
