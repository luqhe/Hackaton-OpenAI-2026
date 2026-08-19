from __future__ import annotations

from datetime import datetime, timedelta
from enum import StrEnum
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, model_validator

from guardian_core.models import EnforcementAction, RiskCategory


class ReviewRole(StrEnum):
    PRODUCT_SAFETY_REVIEWER = "PRODUCT_SAFETY_REVIEWER"
    PRIVACY_REVIEWER = "PRIVACY_REVIEWER"


class ReviewGrant(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    grant_id: str = Field(min_length=1, max_length=120)
    reviewer_subject_digest: str = Field(pattern=r"^[a-f0-9]{64}$")
    role: ReviewRole
    case_reference: str = Field(min_length=1, max_length=120)
    cohort_ids: frozenset[str] = Field(min_length=1)
    categories: frozenset[RiskCategory] = Field(min_length=1)
    valid_from: datetime
    expires_at: datetime
    evidence_access: bool = False

    @model_validator(mode="after")
    def validate_window(self) -> ReviewGrant:
        if self.valid_from.tzinfo is None or self.expires_at.tzinfo is None:
            raise ValueError("Review grants require timezone-aware timestamps")
        if self.expires_at <= self.valid_from:
            raise ValueError("Review grant expiry must follow its start")
        if self.expires_at - self.valid_from > timedelta(hours=1):
            raise ValueError("Review grants may last at most one hour")
        return self


class PilotReviewEvent(BaseModel):
    """Minimum review projection; observed text and binary evidence are excluded."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    event_id: str = Field(min_length=1, max_length=120)
    cohort_id: str = Field(min_length=1, max_length=120)
    category: RiskCategory
    occurred_at: datetime
    confidence: float = Field(ge=0, le=1)
    proposed_action: EnforcementAction
    effective_action: EnforcementAction
    context_digest: str = Field(pattern=r"^[a-f0-9]{64}$")
    evidence_object_id: str | None = Field(default=None, min_length=1, max_length=160)


class PilotReviewView(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    event_id: str
    cohort_id: str
    category: RiskCategory
    occurred_at: datetime
    confidence: float
    proposed_action: EnforcementAction
    effective_action: EnforcementAction
    context_digest: str
    evidence_object_id: str | None = None


class ReviewAuditEntry(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: str = "guardian.pilot-review-audit.v1"
    event_id: str
    grant_id: str
    reviewer_subject_digest: str
    case_reference: str
    accessed_at: datetime
    accessed_fields: tuple[str, ...]
    evidence_disclosed: bool


class ReviewAuditStore:
    def __init__(self, path: Path) -> None:
        self.path = path

    def append(self, entry: ReviewAuditEntry) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as stream:
            stream.write(entry.model_dump_json() + "\n")

    def load(self) -> list[ReviewAuditEntry]:
        if not self.path.exists():
            return []
        return [
            ReviewAuditEntry.model_validate_json(line)
            for line in self.path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]


BASE_REVIEW_FIELDS = (
    "event_id",
    "cohort_id",
    "category",
    "occurred_at",
    "confidence",
    "proposed_action",
    "effective_action",
    "context_digest",
)


def review_event(
    event: PilotReviewEvent,
    grant: ReviewGrant,
    *,
    accessed_at: datetime,
    include_evidence: bool = False,
) -> tuple[PilotReviewView, ReviewAuditEntry]:
    if accessed_at.tzinfo is None:
        raise PermissionError("Review access requires a timezone-aware timestamp")
    if not grant.valid_from <= accessed_at < grant.expires_at:
        raise PermissionError("Review grant is not active")
    if event.cohort_id not in grant.cohort_ids or event.category not in grant.categories:
        raise PermissionError("Review grant does not cover this event scope")
    if include_evidence and not grant.evidence_access:
        raise PermissionError("Review grant does not permit evidence access")

    evidence_object_id = event.evidence_object_id if include_evidence else None
    accessed_fields = BASE_REVIEW_FIELDS + (("evidence_object_id",) if include_evidence else ())
    view = PilotReviewView(
        **event.model_dump(exclude={"evidence_object_id"}),
        evidence_object_id=evidence_object_id,
    )
    audit = ReviewAuditEntry(
        event_id=event.event_id,
        grant_id=grant.grant_id,
        reviewer_subject_digest=grant.reviewer_subject_digest,
        case_reference=grant.case_reference,
        accessed_at=accessed_at,
        accessed_fields=accessed_fields,
        evidence_disclosed=evidence_object_id is not None,
    )
    return view, audit
