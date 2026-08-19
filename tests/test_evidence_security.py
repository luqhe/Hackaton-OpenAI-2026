from __future__ import annotations

import io
import stat
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from api.data_security.evidence import (
    AuthenticatedSubject,
    EvidenceNotFound,
    EvidenceService,
    FileSystemObjectStore,
    InMemoryAuthorizationState,
    InMemoryEvidenceRepository,
    S3ObjectStore,
)
from guardian_core.config import Environment
from guardian_core.identity import FamilyScope, MembershipRole


class _Clock:
    def __init__(self, current: datetime):
        self.current = current

    def __call__(self) -> datetime:
        return self.current


class _RecordingS3Client:
    def __init__(self) -> None:
        self.put_kwargs: dict[str, object] = {}
        self.objects: dict[str, bytes] = {}
        self.deleted: list[str] = []

    def put_object(self, **kwargs: object) -> None:
        self.put_kwargs = kwargs
        self.objects[str(kwargs["Key"])] = bytes(kwargs["Body"])

    def get_object(self, **kwargs: object) -> dict[str, io.BytesIO]:
        return {"Body": io.BytesIO(self.objects[str(kwargs["Key"])])}

    def delete_object(self, **kwargs: object) -> None:
        key = str(kwargs["Key"])
        self.objects.pop(key, None)
        self.deleted.append(key)

    def head_object(self, **kwargs: object) -> dict[str, int]:
        data = self.objects[str(kwargs["Key"])]
        return {"ContentLength": len(data)}


class _UnavailableS3Client(_RecordingS3Client):
    def get_object(self, **kwargs: object) -> dict[str, io.BytesIO]:
        raise RuntimeError("provider unavailable")


def test_s3_upload_requires_kms_and_never_sets_public_acl() -> None:
    client = _RecordingS3Client()
    store = S3ObjectStore(client, bucket="guardian-private", kms_key_id="kms-123")

    store.put("evidence/opaque-key", b"minimal", "text/plain")

    assert client.put_kwargs == {
        "Bucket": "guardian-private",
        "Key": "evidence/opaque-key",
        "Body": b"minimal",
        "ContentType": "text/plain",
        "ServerSideEncryption": "aws:kms",
        "SSEKMSKeyId": "kms-123",
    }


def test_s3_store_rejects_missing_kms_configuration() -> None:
    with pytest.raises(ValueError, match="KMS"):
        S3ObjectStore(_RecordingS3Client(), bucket="guardian-private", kms_key_id="")


def test_s3_store_does_not_misreport_provider_outage_as_missing() -> None:
    store = S3ObjectStore(
        _UnavailableS3Client(),
        bucket="guardian-private",
        kms_key_id="kms-123",
    )

    with pytest.raises(RuntimeError, match="provider unavailable"):
        store.get("evidence/opaque-key")


def test_filesystem_store_is_local_only_private_and_confined(tmp_path: Path) -> None:
    store = FileSystemObjectStore(tmp_path / "evidence", Environment.TEST)
    store.put("evidence/opaque-key", b"minimal", "text/plain")

    stored = tmp_path / "evidence" / "evidence" / "opaque-key"
    assert store.get("evidence/opaque-key") == b"minimal"
    assert stat.S_IMODE(stored.stat().st_mode) == 0o600
    assert stat.S_IMODE((tmp_path / "evidence").stat().st_mode) == 0o700
    with pytest.raises(ValueError, match="object key"):
        store.put("../escape", b"bad", "text/plain")
    with pytest.raises(ValueError, match="development and test"):
        FileSystemObjectStore(tmp_path / "production", Environment.PRODUCTION)


@pytest.fixture
def evidence_context(tmp_path: Path):
    now = datetime(2026, 8, 19, 12, tzinfo=UTC)
    clock = _Clock(now)
    repository = InMemoryEvidenceRepository()
    authorization = InMemoryAuthorizationState()
    service = EvidenceService(
        object_store=FileSystemObjectStore(tmp_path / "objects", Environment.TEST),
        repository=repository,
        authorization=authorization,
        clock=clock,
    )
    scope = FamilyScope(
        account_id="account-1",
        family_id="family-1",
        membership_id="membership-1",
        role=MembershipRole.OWNER,
    )
    repository.register_incident(scope.family_id, "incident-1")
    subject = AuthenticatedSubject(
        principal_id="account-1",
        session_id="session-1",
        revocation_epoch=0,
    )
    authorization.register(scope.family_id, subject)
    evidence = service.store(
        scope,
        incident_id="incident-1",
        data=b"minimal incident excerpt",
        content_type="text/plain",
        retention=timedelta(days=30),
    )
    return service, repository, authorization, clock, scope, subject, evidence


def test_delivery_revalidates_scope_session_epoch_and_expiry(evidence_context) -> None:
    service, _, authorization, clock, scope, subject, evidence = evidence_context
    grant = service.issue_grant(
        scope,
        evidence.id,
        subject,
        ttl=timedelta(minutes=2),
    )

    assert grant.url == f"/api/evidence/access/{grant.token}"
    assert service.deliver(scope, grant.token, subject) == b"minimal incident excerpt"

    authorization.revoke_session(subject.session_id)
    with pytest.raises(EvidenceNotFound, match="Evidence not found"):
        service.deliver(scope, grant.token, subject)

    authorization.register(scope.family_id, subject)
    clock.current += timedelta(minutes=3)
    with pytest.raises(EvidenceNotFound, match="Evidence not found"):
        service.deliver(scope, grant.token, subject)


def test_advanced_family_epoch_revokes_existing_grants(evidence_context) -> None:
    service, _, authorization, _, scope, subject, evidence = evidence_context
    grant = service.issue_grant(scope, evidence.id, subject, ttl=timedelta(minutes=2))

    authorization.advance_family_epoch(scope.family_id)

    with pytest.raises(EvidenceNotFound, match="Evidence not found"):
        service.deliver(scope, grant.token, subject)


def test_foreign_and_missing_evidence_are_indistinguishable(evidence_context) -> None:
    service, _, authorization, _, scope, subject, evidence = evidence_context
    foreign_scope = FamilyScope(
        account_id="account-2",
        family_id="family-2",
        membership_id="membership-2",
        role=MembershipRole.OWNER,
    )
    foreign_subject = AuthenticatedSubject("account-2", "session-2", 0)
    authorization.register(foreign_scope.family_id, foreign_subject)

    errors: list[str] = []
    for requested_scope, evidence_id, requested_subject in (
        (foreign_scope, evidence.id, foreign_subject),
        (scope, "evidence-missing", subject),
    ):
        with pytest.raises(EvidenceNotFound) as captured:
            service.issue_grant(
                requested_scope,
                evidence_id,
                requested_subject,
                ttl=timedelta(minutes=1),
            )
        errors.append(str(captured.value))

    assert errors == ["Evidence not found", "Evidence not found"]


def test_raw_grant_token_is_never_persisted(evidence_context) -> None:
    service, repository, _, _, scope, subject, evidence = evidence_context
    grant = service.issue_grant(scope, evidence.id, subject, ttl=timedelta(minutes=1))

    persisted = repository.grants_for_family(scope.family_id)

    assert len(persisted) == 1
    assert persisted[0].token_digest != grant.token
    assert grant.token not in repr(persisted)


def test_revoked_or_deleted_evidence_cannot_be_delivered(evidence_context) -> None:
    service, repository, _, clock, scope, subject, evidence = evidence_context
    grant = service.issue_grant(scope, evidence.id, subject, ttl=timedelta(minutes=1))
    service.revoke_grants(scope, evidence.id)

    with pytest.raises(EvidenceNotFound):
        service.deliver(scope, grant.token, subject)

    second = service.issue_grant(scope, evidence.id, subject, ttl=timedelta(minutes=1))
    repository.mark_deleted(scope.family_id, evidence.id, clock())
    with pytest.raises(EvidenceNotFound):
        service.deliver(scope, second.token, subject)
