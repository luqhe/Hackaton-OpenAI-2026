from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from guardian_core.models import RiskCategory
from guardian_core.pilot_metrics import (
    ClassificationOutcome,
    FamilyPilotSurvey,
    summarize_pilot_metrics,
)

NOW = datetime(2026, 8, 20, 15, tzinfo=UTC)


def outcome(
    event_id: str,
    *,
    human_confirmed_risk: bool,
    contested: bool = False,
    cohort_id: str = "pilot-alert-a",
) -> ClassificationOutcome:
    return ClassificationOutcome(
        event_id=event_id,
        cohort_id=cohort_id,
        category=RiskCategory.DANGEROUS_CONTACT,
        model_flagged=True,
        human_reviewed=True,
        human_confirmed_risk=human_confirmed_risk,
        incident_shown=True,
        contested=contested,
    )


def surveys(count: int, *, cohort_id: str = "pilot-alert-a") -> list[FamilyPilotSurvey]:
    return [
        FamilyPilotSurvey(
            response_id=f"response-{index}",
            cohort_id=cohort_id,
            family_subject_digest=f"{index:064x}",
            submitted_at=NOW,
            intervention_comprehension=3 + index % 3,
            guardian_confidence=4,
        )
        for index in range(count)
    ]


def test_metrics_use_explicit_review_and_incident_denominators() -> None:
    summary = summarize_pilot_metrics(
        "pilot-alert-a",
        [
            outcome("confirmed", human_confirmed_risk=True),
            outcome("fp", human_confirmed_risk=False, contested=True),
        ],
        surveys(5),
    )

    assert summary.reviewed_flagged_events == 2
    assert summary.false_positives == 1
    assert summary.false_positive_rate == 0.5
    assert summary.incidents_shown == 2
    assert summary.contested_incidents == 1
    assert summary.contestation_rate == 0.5
    assert summary.intervention_comprehension_mean == 3.8
    assert summary.guardian_confidence_mean == 4
    assert summary.feedback_suppressed is False


def test_small_feedback_samples_are_suppressed() -> None:
    summary = summarize_pilot_metrics(
        "pilot-alert-a",
        [outcome("confirmed", human_confirmed_risk=True)],
        surveys(2),
    )

    assert summary.survey_responses == 2
    assert summary.intervention_comprehension_mean is None
    assert summary.guardian_confidence_mean is None
    assert summary.feedback_suppressed is True


def test_summary_isolated_by_cohort() -> None:
    summary = summarize_pilot_metrics(
        "pilot-alert-a",
        [
            outcome("in-scope", human_confirmed_risk=True),
            outcome("other", human_confirmed_risk=False, cohort_id="other-cohort"),
        ],
        surveys(5) + surveys(5, cohort_id="other-cohort"),
    )

    assert summary.classification_events == 1
    assert summary.survey_responses == 5
    assert summary.false_positives == 0


def test_feedback_contract_rejects_free_text_and_invalid_outcomes() -> None:
    with pytest.raises(ValidationError, match="Extra inputs"):
        FamilyPilotSurvey.model_validate({**surveys(1)[0].model_dump(mode="json"), "comment": "raw text"})

    with pytest.raises(ValidationError, match="requires incident_shown"):
        ClassificationOutcome.model_validate(
            {
                **outcome("bad", human_confirmed_risk=True).model_dump(mode="json"),
                "incident_shown": False,
                "contested": True,
            }
        )


def test_feedback_sample_floor_is_validated() -> None:
    with pytest.raises(ValueError, match="at least 2"):
        summarize_pilot_metrics("pilot-alert-a", [], [], minimum_feedback_sample=1)


def test_retries_do_not_inflate_events_responses_or_families() -> None:
    event = outcome("idempotent-event", human_confirmed_risk=False, contested=True)
    responses = surveys(5)
    summary = summarize_pilot_metrics(
        "pilot-alert-a",
        [event, event],
        responses + [responses[0]],
    )

    assert summary.classification_events == 1
    assert summary.false_positives == 1
    assert summary.contested_incidents == 1
    assert summary.survey_responses == 5
    assert summary.unique_families == 5


def test_only_latest_response_per_family_contributes_to_feedback() -> None:
    original = surveys(5)
    replacement = original[0].model_copy(
        update={
            "response_id": "response-0-newer",
            "submitted_at": NOW.replace(hour=16),
            "intervention_comprehension": 1,
            "guardian_confidence": 1,
        }
    )
    summary = summarize_pilot_metrics(
        "pilot-alert-a",
        [],
        original + [replacement],
    )

    assert summary.survey_responses == 5
    assert summary.unique_families == 5
    assert summary.intervention_comprehension_mean == 3.4
    assert summary.guardian_confidence_mean == 3.4


def test_conflicting_duplicate_event_is_rejected() -> None:
    event = outcome("conflict", human_confirmed_risk=True)
    conflicting = event.model_copy(update={"human_confirmed_risk": False})

    with pytest.raises(ValueError, match="Conflicting classification outcome"):
        summarize_pilot_metrics("pilot-alert-a", [event, conflicting], [])
