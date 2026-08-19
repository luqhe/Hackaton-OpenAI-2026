from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from pydantic import ValidationError

from guardian_core.models import EnforcementAction, RiskCategory
from guardian_core.pilot_review import (
    PilotReviewEvent,
    ReviewAuditStore,
    ReviewGrant,
    ReviewRole,
    review_event,
)

NOW = datetime(2026, 8, 20, 12, tzinfo=UTC)
DIGEST = "a" * 64


def event() -> PilotReviewEvent:
    return PilotReviewEvent(
        event_id="event-42",
        cohort_id="pilot-alert-a",
        category=RiskCategory.DANGEROUS_CONTACT,
        occurred_at=NOW - timedelta(minutes=2),
        confidence=0.97,
        proposed_action=EnforcementAction.BLOCK,
        effective_action=EnforcementAction.ALERT,
        context_digest="b" * 64,
        evidence_object_id="evidence/object-42",
    )


def grant(*, evidence_access: bool = False) -> ReviewGrant:
    return ReviewGrant(
        grant_id="grant-7",
        reviewer_subject_digest=DIGEST,
        role=ReviewRole.PRODUCT_SAFETY_REVIEWER,
        case_reference="PS-2026-0042",
        cohort_ids=frozenset({"pilot-alert-a"}),
        categories=frozenset({RiskCategory.DANGEROUS_CONTACT}),
        valid_from=NOW - timedelta(minutes=5),
        expires_at=NOW + timedelta(minutes=25),
        evidence_access=evidence_access,
    )


def test_metadata_review_excludes_evidence_and_writes_minimum_audit(tmp_path: Path) -> None:
    store = ReviewAuditStore(tmp_path / "review-audit.jsonl")
    view = review_event(event(), grant(), audit_store=store, accessed_at=NOW)
    audit = store.load()[0]

    assert view.evidence_object_id is None
    assert audit.evidence_disclosed is False
    assert audit.reviewer_subject_digest == DIGEST
    assert "evidence_object_id" not in audit.accessed_fields
    assert store.load() == [audit]


def test_evidence_requires_explicit_scoped_access(tmp_path: Path) -> None:
    store = ReviewAuditStore(tmp_path / "review-audit.jsonl")
    with pytest.raises(PermissionError, match="evidence"):
        review_event(event(), grant(), audit_store=store, accessed_at=NOW, include_evidence=True)

    view = review_event(
        event(),
        grant(evidence_access=True),
        audit_store=store,
        accessed_at=NOW,
        include_evidence=True,
    )
    assert view.evidence_object_id == "evidence/object-42"
    assert store.load()[0].evidence_disclosed is True


@pytest.mark.parametrize(
    ("accessed_at", "cohort_id"),
    [
        (NOW + timedelta(hours=2), "pilot-alert-a"),
        (NOW, "another-cohort"),
    ],
)
def test_review_rejects_expired_or_out_of_scope_access(
    accessed_at: datetime,
    cohort_id: str,
    tmp_path: Path,
) -> None:
    candidate = event().model_copy(update={"cohort_id": cohort_id})
    with pytest.raises(PermissionError):
        review_event(
            candidate,
            grant(),
            audit_store=ReviewAuditStore(tmp_path / "audit.jsonl"),
            accessed_at=accessed_at,
        )


def test_review_contract_rejects_raw_content_and_long_lived_grants() -> None:
    with pytest.raises(ValidationError, match="Extra inputs"):
        PilotReviewEvent.model_validate({**event().model_dump(mode="json"), "visible_text": "secret"})

    with pytest.raises(ValidationError, match="at most one hour"):
        ReviewGrant.model_validate(
            {
                **grant().model_dump(mode="json"),
                "expires_at": NOW + timedelta(hours=2),
            }
        )


def test_review_is_not_returned_when_mandatory_audit_fails(monkeypatch, tmp_path: Path) -> None:
    store = ReviewAuditStore(tmp_path / "review-audit.jsonl")

    def fail_audit(entry) -> None:
        raise OSError("audit storage unavailable")

    monkeypatch.setattr(store, "append", fail_audit)
    with pytest.raises(OSError, match="audit storage unavailable"):
        review_event(event(), grant(), audit_store=store, accessed_at=NOW)

    assert store.load() == []
