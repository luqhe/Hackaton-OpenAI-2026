from __future__ import annotations

import hashlib
import hmac
import json
import re
import threading
import uuid
from collections.abc import Callable, Mapping
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import Protocol

from guardian_core.config import Environment

OPAQUE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,159}$")
ZERO_HASH = "0" * 64


def _utc_now() -> datetime:
    return datetime.now(UTC)


class AuditActorType(StrEnum):
    ACCOUNT = "ACCOUNT"
    DEVICE = "DEVICE"
    SYSTEM = "SYSTEM"
    SUPPORT = "SUPPORT"


class AuditAction(StrEnum):
    POLICY_VIEWED = "POLICY_VIEWED"
    POLICY_UPDATED = "POLICY_UPDATED"
    EVIDENCE_STORED = "EVIDENCE_STORED"
    EVIDENCE_ACCESSED = "EVIDENCE_ACCESSED"
    EVIDENCE_ACCESS_DENIED = "EVIDENCE_ACCESS_DENIED"
    EVIDENCE_DELETED = "EVIDENCE_DELETED"
    INCIDENT_DECIDED = "INCIDENT_DECIDED"
    FAMILY_EXPORTED = "FAMILY_EXPORTED"
    FAMILY_DELETION_REQUESTED = "FAMILY_DELETION_REQUESTED"
    RATE_LIMITED = "RATE_LIMITED"


class AuditTargetType(StrEnum):
    POLICY = "POLICY"
    EVIDENCE = "EVIDENCE"
    INCIDENT = "INCIDENT"
    FAMILY = "FAMILY"
    COMMAND = "COMMAND"
    SESSION = "SESSION"


class AuditResult(StrEnum):
    SUCCESS = "SUCCESS"
    DENIED = "DENIED"
    ERROR = "ERROR"


@dataclass(frozen=True, slots=True)
class AuditInput:
    family_id: str
    actor_type: AuditActorType
    actor_id: str
    action: AuditAction
    target_type: AuditTargetType
    target_id: str
    result: AuditResult
    correlation_id: str

    def __post_init__(self) -> None:
        for name in ("family_id", "actor_id", "target_id", "correlation_id"):
            if not OPAQUE_ID.fullmatch(getattr(self, name)):
                raise ValueError(f"Audit {name} must be a bounded opaque identifier")


@dataclass(frozen=True, slots=True)
class AuditRecord:
    sequence: int
    event_id: str
    occurred_at: datetime
    family_id: str
    actor_type: AuditActorType
    actor_id: str
    action: AuditAction
    target_type: AuditTargetType
    target_id: str
    result: AuditResult
    correlation_id: str
    key_id: str
    previous_hash: str
    event_hash: str


@dataclass(frozen=True, slots=True)
class AuditCheckpoint:
    sequence: int
    event_hash: str
    key_id: str
    checkpoint_hash: str
    created_at: datetime


@dataclass(frozen=True, slots=True)
class AuditVerification:
    valid: bool
    checked_records: int
    reason: str | None = None


class AuditKeyring:
    def __init__(
        self,
        *,
        current_key_id: str,
        keys: Mapping[str, bytes],
        environment: Environment,
    ):
        self.environment = environment
        self._keys = dict(keys)
        self.current_key_id = current_key_id
        self._validate_key(current_key_id, self._keys.get(current_key_id))

    def _validate_key(self, key_id: str, secret: bytes | None) -> None:
        if not key_id or secret is None:
            raise ValueError("A current audit HMAC key_id and secret are required")
        if len(secret) < 32:
            raise ValueError("Managed audit HMAC secrets must contain at least 32 bytes")
        if self.environment in {Environment.STAGING, Environment.PRODUCTION} and secret in {
            b"development-only",
            b"test-only",
        }:
            raise ValueError("Managed audit HMAC secret cannot use a development default")

    def rotate(self, key_id: str, secret: bytes) -> None:
        self._validate_key(key_id, secret)
        self._keys[key_id] = secret
        self.current_key_id = key_id

    def get(self, key_id: str) -> bytes | None:
        return self._keys.get(key_id)

    @property
    def current_secret(self) -> bytes:
        secret = self.get(self.current_key_id)
        if secret is None:
            raise RuntimeError("Current audit key is unavailable")
        return secret


RecordFactory = Callable[[int, str], AuditRecord]


class AuditRepository(Protocol):
    def append_atomic(self, factory: RecordFactory) -> AuditRecord: ...

    def all(self) -> list[AuditRecord]: ...


class InMemoryAuditRepository:
    def __init__(self) -> None:
        self.records: list[AuditRecord] = []
        self._lock = threading.Lock()

    def append_atomic(self, factory: RecordFactory) -> AuditRecord:
        with self._lock:
            sequence = len(self.records) + 1
            previous_hash = self.records[-1].event_hash if self.records else ZERO_HASH
            record = factory(sequence, previous_hash)
            self.records.append(record)
            return record

    def all(self) -> list[AuditRecord]:
        return list(self.records)


class AuditTrail:
    def __init__(
        self,
        repository: AuditRepository,
        keyring: AuditKeyring,
        *,
        clock: Callable[[], datetime] = _utc_now,
    ):
        self.repository = repository
        self.keyring = keyring
        self.clock = clock

    def append(self, event: AuditInput) -> AuditRecord:
        occurred_at = self.clock()
        event_id = f"audit-{uuid.uuid4().hex}"
        key_id = self.keyring.current_key_id
        secret = self.keyring.current_secret

        def build(sequence: int, previous_hash: str) -> AuditRecord:
            unsigned = {
                "sequence": sequence,
                "event_id": event_id,
                "occurred_at": occurred_at.isoformat(),
                **asdict(event),
                "key_id": key_id,
                "previous_hash": previous_hash,
            }
            return AuditRecord(
                sequence=sequence,
                event_id=event_id,
                occurred_at=occurred_at,
                **asdict(event),
                key_id=key_id,
                previous_hash=previous_hash,
                event_hash=_sign(secret, unsigned),
            )

        return self.repository.append_atomic(build)

    def checkpoint(self) -> AuditCheckpoint:
        records = self.repository.all()
        if not records:
            raise ValueError("Cannot checkpoint an empty audit trail")
        latest = records[-1]
        created_at = self.clock()
        key_id = self.keyring.current_key_id
        unsigned = {
            "sequence": latest.sequence,
            "event_hash": latest.event_hash,
            "key_id": key_id,
            "created_at": created_at.isoformat(),
        }
        return AuditCheckpoint(
            sequence=latest.sequence,
            event_hash=latest.event_hash,
            key_id=key_id,
            checkpoint_hash=_sign(self.keyring.current_secret, unsigned),
            created_at=created_at,
        )

    def verify(self, *, checkpoint: AuditCheckpoint | None = None) -> AuditVerification:
        records = self.repository.all()
        previous_hash = ZERO_HASH
        for expected_sequence, record in enumerate(records, start=1):
            if record.sequence != expected_sequence or record.previous_hash != previous_hash:
                return AuditVerification(False, expected_sequence - 1, "sequence or link mismatch")
            secret = self.keyring.get(record.key_id)
            if secret is None:
                return AuditVerification(False, expected_sequence - 1, "verification key unavailable")
            unsigned = {
                "sequence": record.sequence,
                "event_id": record.event_id,
                "occurred_at": record.occurred_at.isoformat(),
                "family_id": record.family_id,
                "actor_type": record.actor_type,
                "actor_id": record.actor_id,
                "action": record.action,
                "target_type": record.target_type,
                "target_id": record.target_id,
                "result": record.result,
                "correlation_id": record.correlation_id,
                "key_id": record.key_id,
                "previous_hash": record.previous_hash,
            }
            expected_hash = _sign(secret, unsigned)
            if not hmac.compare_digest(record.event_hash, expected_hash):
                return AuditVerification(False, expected_sequence - 1, "event hash mismatch")
            previous_hash = record.event_hash

        if checkpoint is not None and not self._verify_checkpoint(records, checkpoint):
            return AuditVerification(False, len(records), "checkpoint mismatch")
        return AuditVerification(True, len(records))

    def _verify_checkpoint(self, records: list[AuditRecord], checkpoint: AuditCheckpoint) -> bool:
        if checkpoint.sequence < 1 or checkpoint.sequence > len(records):
            return False
        record = records[checkpoint.sequence - 1]
        if record.event_hash != checkpoint.event_hash:
            return False
        secret = self.keyring.get(checkpoint.key_id)
        if secret is None:
            return False
        unsigned = {
            "sequence": checkpoint.sequence,
            "event_hash": checkpoint.event_hash,
            "key_id": checkpoint.key_id,
            "created_at": checkpoint.created_at.isoformat(),
        }
        return hmac.compare_digest(checkpoint.checkpoint_hash, _sign(secret, unsigned))


def _sign(secret: bytes, payload: Mapping[str, object]) -> str:
    canonical = json.dumps(
        payload,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode()
    return hmac.new(secret, canonical, hashlib.sha256).hexdigest()
