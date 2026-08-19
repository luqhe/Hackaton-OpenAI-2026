from __future__ import annotations

import hashlib
import re
import secrets
import uuid
from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Protocol

from guardian_core.config import Environment
from guardian_core.identity import FamilyScope

MAX_EVIDENCE_BYTES = 4 * 1024 * 1024
MAX_GRANT_TTL = timedelta(minutes=5)
ALLOWED_CONTENT_TYPES = {"image/png", "image/jpeg", "image/webp", "text/plain"}
OBJECT_KEY_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_-]*(?:/[a-z0-9][a-z0-9_-]*)*$")


def _utc_now() -> datetime:
    return datetime.now(UTC)


class EvidenceNotFound(LookupError):
    def __init__(self):
        super().__init__("Evidence not found")


class ObjectNotFound(LookupError):
    pass


class ObjectStore(Protocol):
    def put(self, object_key: str, data: bytes, content_type: str) -> None: ...

    def get(self, object_key: str) -> bytes: ...

    def delete(self, object_key: str) -> None: ...

    def exists(self, object_key: str) -> bool: ...


class FileSystemObjectStore:
    def __init__(self, root: Path, environment: Environment):
        if environment not in {Environment.DEVELOPMENT, Environment.TEST}:
            raise ValueError("Filesystem evidence storage is restricted to development and test")
        self.root = root.resolve()
        self.root.mkdir(parents=True, mode=0o700, exist_ok=True)
        self.root.chmod(0o700)

    def put(self, object_key: str, data: bytes, content_type: str) -> None:
        del content_type
        destination = self._resolve(object_key)
        destination.parent.mkdir(parents=True, mode=0o700, exist_ok=True)
        destination.parent.chmod(0o700)
        with destination.open("xb") as output:
            output.write(data)
        destination.chmod(0o600)

    def get(self, object_key: str) -> bytes:
        path = self._resolve(object_key)
        try:
            return path.read_bytes()
        except FileNotFoundError as error:
            raise ObjectNotFound(object_key) from error

    def delete(self, object_key: str) -> None:
        self._resolve(object_key).unlink(missing_ok=True)

    def exists(self, object_key: str) -> bool:
        return self._resolve(object_key).is_file()

    def _resolve(self, object_key: str) -> Path:
        _validate_object_key(object_key)
        path = (self.root / object_key).resolve()
        if self.root not in path.parents:
            raise ValueError("Invalid object key")
        return path


class S3ObjectStore:
    """Private S3-compatible adapter. The provider client is injected."""

    def __init__(
        self,
        client: Any,
        *,
        bucket: str,
        kms_key_id: str,
        not_found_exceptions: tuple[type[Exception], ...] = (),
    ):
        if not bucket or not bucket.strip():
            raise ValueError("A private object-storage bucket is required")
        if not kms_key_id or not kms_key_id.strip():
            raise ValueError("A KMS key is required for managed evidence storage")
        self.client = client
        self.bucket = bucket
        self.kms_key_id = kms_key_id
        self.not_found_exceptions = not_found_exceptions

    def put(self, object_key: str, data: bytes, content_type: str) -> None:
        _validate_object_key(object_key)
        self.client.put_object(
            Bucket=self.bucket,
            Key=object_key,
            Body=data,
            ContentType=content_type,
            ServerSideEncryption="aws:kms",
            SSEKMSKeyId=self.kms_key_id,
        )

    def get(self, object_key: str) -> bytes:
        _validate_object_key(object_key)
        try:
            response = self.client.get_object(Bucket=self.bucket, Key=object_key)
            return bytes(response["Body"].read())
        except Exception as error:
            if isinstance(error, self.not_found_exceptions):
                raise ObjectNotFound(object_key) from error
            raise

    def delete(self, object_key: str) -> None:
        _validate_object_key(object_key)
        self.client.delete_object(Bucket=self.bucket, Key=object_key)

    def exists(self, object_key: str) -> bool:
        _validate_object_key(object_key)
        try:
            self.client.head_object(Bucket=self.bucket, Key=object_key)
        except Exception as error:
            if isinstance(error, self.not_found_exceptions):
                return False
            raise
        return True


@dataclass(frozen=True, slots=True)
class AuthenticatedSubject:
    principal_id: str
    session_id: str
    revocation_epoch: int

    def __post_init__(self) -> None:
        if not self.principal_id or not self.session_id:
            raise ValueError("Authenticated subject requires principal and session identifiers")
        if self.revocation_epoch < 0:
            raise ValueError("Revocation epoch cannot be negative")


@dataclass(frozen=True, slots=True)
class EvidenceRecord:
    family_id: str
    id: str
    incident_id: str
    object_key: str
    content_type: str
    sha256: str
    size_bytes: int
    created_at: datetime
    expires_at: datetime
    deleted_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class PersistedEvidenceGrant:
    family_id: str
    id: str
    evidence_id: str
    token_digest: str
    principal_id: str
    session_id: str
    revocation_epoch: int
    created_at: datetime
    expires_at: datetime
    revoked_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class TemporaryEvidenceGrant:
    token: str
    url: str
    expires_at: datetime


class EvidenceRepository(Protocol):
    def incident_exists(self, family_id: str, incident_id: str) -> bool: ...

    def add_evidence(self, evidence: EvidenceRecord) -> None: ...

    def get_evidence(self, family_id: str, evidence_id: str) -> EvidenceRecord | None: ...

    def mark_deleted(self, family_id: str, evidence_id: str, deleted_at: datetime) -> None: ...

    def add_grant(self, grant: PersistedEvidenceGrant) -> None: ...

    def get_grant(self, token_digest: str) -> PersistedEvidenceGrant | None: ...

    def revoke_grants(self, family_id: str, evidence_id: str, revoked_at: datetime) -> None: ...


class AuthorizationState(Protocol):
    def is_active(self, scope: FamilyScope, subject: AuthenticatedSubject) -> bool: ...

    def family_epoch(self, family_id: str) -> int: ...


class InMemoryAuthorizationState:
    def __init__(self) -> None:
        self._sessions: dict[str, tuple[str, str, int]] = {}
        self._family_epochs: dict[str, int] = {}

    def register(self, family_id: str, subject: AuthenticatedSubject) -> None:
        current_epoch = self.family_epoch(family_id)
        if subject.revocation_epoch != current_epoch:
            raise ValueError("Subject revocation epoch is stale")
        self._sessions[subject.session_id] = (family_id, subject.principal_id, current_epoch)

    def revoke_session(self, session_id: str) -> None:
        self._sessions.pop(session_id, None)

    def advance_family_epoch(self, family_id: str) -> int:
        next_epoch = self.family_epoch(family_id) + 1
        self._family_epochs[family_id] = next_epoch
        return next_epoch

    def is_active(self, scope: FamilyScope, subject: AuthenticatedSubject) -> bool:
        expected = (scope.family_id, scope.account_id, self.family_epoch(scope.family_id))
        return (
            subject.principal_id == scope.account_id
            and subject.revocation_epoch == expected[2]
            and self._sessions.get(subject.session_id) == expected
        )

    def family_epoch(self, family_id: str) -> int:
        return self._family_epochs.get(family_id, 0)


class InMemoryEvidenceRepository:
    def __init__(self) -> None:
        self._incidents: set[tuple[str, str]] = set()
        self._evidence: dict[tuple[str, str], EvidenceRecord] = {}
        self._grants: dict[str, PersistedEvidenceGrant] = {}

    def register_incident(self, family_id: str, incident_id: str) -> None:
        self._incidents.add((family_id, incident_id))

    def incident_exists(self, family_id: str, incident_id: str) -> bool:
        return (family_id, incident_id) in self._incidents

    def add_evidence(self, evidence: EvidenceRecord) -> None:
        key = (evidence.family_id, evidence.id)
        if key in self._evidence:
            raise ValueError("Evidence already exists")
        self._evidence[key] = evidence

    def get_evidence(self, family_id: str, evidence_id: str) -> EvidenceRecord | None:
        return self._evidence.get((family_id, evidence_id))

    def mark_deleted(self, family_id: str, evidence_id: str, deleted_at: datetime) -> None:
        evidence = self._evidence.get((family_id, evidence_id))
        if evidence is None:
            return
        self._evidence[(family_id, evidence_id)] = replace(evidence, deleted_at=deleted_at)
        self.revoke_grants(family_id, evidence_id, deleted_at)

    def add_grant(self, grant: PersistedEvidenceGrant) -> None:
        if grant.token_digest in self._grants:
            raise ValueError("Evidence grant token digest already exists")
        self._grants[grant.token_digest] = grant

    def get_grant(self, token_digest: str) -> PersistedEvidenceGrant | None:
        return self._grants.get(token_digest)

    def revoke_grants(self, family_id: str, evidence_id: str, revoked_at: datetime) -> None:
        for digest, grant in tuple(self._grants.items()):
            if grant.family_id == family_id and grant.evidence_id == evidence_id:
                self._grants[digest] = replace(grant, revoked_at=grant.revoked_at or revoked_at)

    def grants_for_family(self, family_id: str) -> list[PersistedEvidenceGrant]:
        return [grant for grant in self._grants.values() if grant.family_id == family_id]


class EvidenceService:
    def __init__(
        self,
        *,
        object_store: ObjectStore,
        repository: EvidenceRepository,
        authorization: AuthorizationState,
        clock: Callable[[], datetime] = _utc_now,
    ):
        self.object_store = object_store
        self.repository = repository
        self.authorization = authorization
        self.clock = clock

    def store(
        self,
        scope: FamilyScope,
        *,
        incident_id: str,
        data: bytes,
        content_type: str,
        retention: timedelta,
    ) -> EvidenceRecord:
        if not self.repository.incident_exists(scope.family_id, incident_id):
            raise EvidenceNotFound()
        if content_type not in ALLOWED_CONTENT_TYPES:
            raise ValueError("Unsupported evidence content type")
        if not data or len(data) > MAX_EVIDENCE_BYTES:
            raise ValueError("Evidence must contain between 1 byte and 4 MB")
        if retention <= timedelta(0):
            raise ValueError("Evidence retention must be positive")

        now = self.clock()
        evidence = EvidenceRecord(
            family_id=scope.family_id,
            id=f"ev-{uuid.uuid4().hex}",
            incident_id=incident_id,
            object_key=f"evidence/{uuid.uuid4().hex}",
            content_type=content_type,
            sha256=hashlib.sha256(data).hexdigest(),
            size_bytes=len(data),
            created_at=now,
            expires_at=now + retention,
        )
        self.object_store.put(evidence.object_key, data, content_type)
        try:
            self.repository.add_evidence(evidence)
        except Exception:
            self.object_store.delete(evidence.object_key)
            raise
        return evidence

    def issue_grant(
        self,
        scope: FamilyScope,
        evidence_id: str,
        subject: AuthenticatedSubject,
        *,
        ttl: timedelta,
    ) -> TemporaryEvidenceGrant:
        now = self.clock()
        if not self.authorization.is_active(scope, subject):
            raise EvidenceNotFound()
        if ttl <= timedelta(0) or ttl > MAX_GRANT_TTL:
            raise ValueError("Evidence grant TTL must be between 1 second and 5 minutes")
        evidence = self.repository.get_evidence(scope.family_id, evidence_id)
        if evidence is None or evidence.deleted_at is not None or evidence.expires_at <= now:
            raise EvidenceNotFound()

        expires_at = min(now + ttl, evidence.expires_at)
        raw_token = secrets.token_urlsafe(32)
        digest = _token_digest(raw_token)
        grant = PersistedEvidenceGrant(
            family_id=scope.family_id,
            id=f"grant-{uuid.uuid4().hex}",
            evidence_id=evidence_id,
            token_digest=digest,
            principal_id=subject.principal_id,
            session_id=subject.session_id,
            revocation_epoch=subject.revocation_epoch,
            created_at=now,
            expires_at=expires_at,
        )
        self.repository.add_grant(grant)
        return TemporaryEvidenceGrant(
            token=raw_token,
            url=f"/api/evidence/access/{raw_token}",
            expires_at=expires_at,
        )

    def deliver(
        self,
        scope: FamilyScope,
        raw_token: str,
        subject: AuthenticatedSubject,
    ) -> bytes:
        now = self.clock()
        if not self.authorization.is_active(scope, subject):
            raise EvidenceNotFound()
        grant = self.repository.get_grant(_token_digest(raw_token))
        if (
            grant is None
            or grant.family_id != scope.family_id
            or grant.principal_id != subject.principal_id
            or grant.session_id != subject.session_id
            or grant.revocation_epoch != subject.revocation_epoch
            or grant.revocation_epoch != self.authorization.family_epoch(scope.family_id)
            or grant.revoked_at is not None
            or grant.expires_at <= now
        ):
            raise EvidenceNotFound()
        evidence = self.repository.get_evidence(scope.family_id, grant.evidence_id)
        if evidence is None or evidence.deleted_at is not None or evidence.expires_at <= now:
            raise EvidenceNotFound()
        try:
            return self.object_store.get(evidence.object_key)
        except ObjectNotFound as error:
            raise EvidenceNotFound() from error

    def revoke_grants(self, scope: FamilyScope, evidence_id: str) -> None:
        evidence = self.repository.get_evidence(scope.family_id, evidence_id)
        if evidence is None:
            raise EvidenceNotFound()
        self.repository.revoke_grants(scope.family_id, evidence_id, self.clock())


def _token_digest(raw_token: str) -> str:
    return hashlib.sha256(raw_token.encode()).hexdigest()


def _validate_object_key(object_key: str) -> None:
    if not OBJECT_KEY_PATTERN.fullmatch(object_key):
        raise ValueError("Invalid object key")
