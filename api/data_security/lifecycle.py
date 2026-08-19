from __future__ import annotations

import json
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import Protocol

from api.data_security.evidence import EvidenceRecord
from guardian_core.identity import FamilyScope

FORBIDDEN_EXPORT_FIELDS = {
    "credential",
    "file_path",
    "frame",
    "object_key",
    "ocr",
    "payload",
    "secret",
    "token",
    "visible_text",
}


def _utc_now() -> datetime:
    return datetime.now(UTC)


class DeletionTarget(StrEnum):
    FAMILY = "FAMILY"
    EVIDENCE = "EVIDENCE"


@dataclass(frozen=True, slots=True)
class DeletionTombstone:
    sequence: int
    family_id: str
    target_type: DeletionTarget
    target_id: str
    deleted_at: datetime
    reason: str


@dataclass(frozen=True, slots=True)
class RetentionResult:
    deleted: int
    failed: int


@dataclass(frozen=True, slots=True)
class FamilyDeletionResult:
    completed: bool
    failed_objects: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ReconciliationResult:
    safe_to_open: bool
    last_sequence: int
    failures: tuple[str, ...]


class ObjectDeletionStore(Protocol):
    def delete(self, object_key: str) -> None: ...


class FamilyRevoker(Protocol):
    def revoke_family(self, family_id: str) -> None: ...


class TombstoneLedger(Protocol):
    def append(
        self,
        family_id: str,
        target_type: DeletionTarget,
        target_id: str,
        deleted_at: datetime,
        reason: str,
    ) -> DeletionTombstone: ...

    def after(self, sequence: int) -> list[DeletionTombstone]: ...


class LifecycleRepository(Protocol):
    def expired_evidence(self, now: datetime) -> list[EvidenceRecord]: ...

    def family_evidence(self, family_id: str) -> list[EvidenceRecord]: ...

    def mark_evidence_inaccessible(self, family_id: str, evidence_id: str, deleted_at: datetime) -> None: ...

    def purge_evidence(self, family_id: str, evidence_id: str) -> None: ...

    def family_exists(self, family_id: str) -> bool: ...

    def export_records(self, family_id: str) -> list[Mapping[str, object]]: ...

    def mark_family_inaccessible(self, family_id: str) -> None: ...

    def delete_family_rows(self, family_id: str) -> None: ...

    def delete_family_for_restore(self, family_id: str) -> None: ...

    def delete_evidence_for_restore(self, family_id: str, evidence_id: str) -> None: ...

    def is_tombstone_applied(self, tombstone: DeletionTombstone) -> bool: ...


class InMemoryTombstoneLedger:
    def __init__(self, *, call_log: list[tuple[str, str]] | None = None):
        self._records: list[DeletionTombstone] = []
        self._by_target: dict[tuple[str, DeletionTarget, str], DeletionTombstone] = {}
        self._call_log = call_log

    def append(
        self,
        family_id: str,
        target_type: DeletionTarget,
        target_id: str,
        deleted_at: datetime,
        reason: str,
    ) -> DeletionTombstone:
        key = (family_id, target_type, target_id)
        existing = self._by_target.get(key)
        if existing is not None:
            return existing
        record = DeletionTombstone(
            sequence=len(self._records) + 1,
            family_id=family_id,
            target_type=target_type,
            target_id=target_id,
            deleted_at=deleted_at,
            reason=reason,
        )
        self._records.append(record)
        self._by_target[key] = record
        if self._call_log is not None:
            self._call_log.append(("tombstone", target_id))
        return record

    def after(self, sequence: int) -> list[DeletionTombstone]:
        return [record for record in self._records if record.sequence > sequence]

    def all(self) -> list[DeletionTombstone]:
        return list(self._records)


class InMemoryRevoker:
    def __init__(self, *, call_log: list[tuple[str, str]] | None = None):
        self.revoked_families: list[str] = []
        self._call_log = call_log

    def revoke_family(self, family_id: str) -> None:
        if family_id not in self.revoked_families:
            self.revoked_families.append(family_id)
        if self._call_log is not None:
            self._call_log.append(("revoke", family_id))


class InMemoryLifecycleRepository:
    def __init__(self, *, call_log: list[tuple[str, str]] | None = None):
        self._families: dict[str, list[Mapping[str, object]]] = {}
        self._inaccessible_families: set[str] = set()
        self._evidence: dict[tuple[str, str], EvidenceRecord] = {}
        self._inaccessible_evidence: set[tuple[str, str]] = set()
        self._call_log = call_log

    def register_family(self, family_id: str, *, records: list[Mapping[str, object]]) -> None:
        self._families[family_id] = list(records)

    def add_evidence(self, evidence: EvidenceRecord) -> None:
        self._evidence[(evidence.family_id, evidence.id)] = evidence

    def get_evidence(self, family_id: str, evidence_id: str) -> EvidenceRecord | None:
        return self._evidence.get((family_id, evidence_id))

    def expired_evidence(self, now: datetime) -> list[EvidenceRecord]:
        return [item for item in self._evidence.values() if item.expires_at <= now]

    def family_evidence(self, family_id: str) -> list[EvidenceRecord]:
        return [item for item in self._evidence.values() if item.family_id == family_id]

    def mark_evidence_inaccessible(self, family_id: str, evidence_id: str, deleted_at: datetime) -> None:
        del deleted_at
        self._inaccessible_evidence.add((family_id, evidence_id))
        if self._call_log is not None:
            self._call_log.append(("inaccessible", evidence_id))

    def purge_evidence(self, family_id: str, evidence_id: str) -> None:
        self._evidence.pop((family_id, evidence_id), None)
        self._inaccessible_evidence.add((family_id, evidence_id))

    def is_evidence_accessible(self, family_id: str, evidence_id: str) -> bool:
        key = (family_id, evidence_id)
        return (
            key in self._evidence
            and key not in self._inaccessible_evidence
            and family_id not in self._inaccessible_families
        )

    def family_exists(self, family_id: str) -> bool:
        return family_id in self._families

    def export_records(self, family_id: str) -> list[Mapping[str, object]]:
        return list(self._families[family_id])

    def mark_family_inaccessible(self, family_id: str) -> None:
        self._inaccessible_families.add(family_id)
        if self._call_log is not None:
            self._call_log.append(("family_inaccessible", family_id))

    def delete_family_rows(self, family_id: str) -> None:
        self._families.pop(family_id, None)
        for key in tuple(self._evidence):
            if key[0] == family_id:
                self._evidence.pop(key, None)
        if self._call_log is not None:
            self._call_log.append(("delete_rows", family_id))

    def delete_family_for_restore(self, family_id: str) -> None:
        self.mark_family_inaccessible(family_id)
        self.delete_family_rows(family_id)

    def delete_evidence_for_restore(self, family_id: str, evidence_id: str) -> None:
        self.mark_evidence_inaccessible(family_id, evidence_id, _utc_now())
        self.purge_evidence(family_id, evidence_id)

    def is_tombstone_applied(self, tombstone: DeletionTombstone) -> bool:
        if tombstone.target_type == DeletionTarget.FAMILY:
            return not self.family_exists(tombstone.family_id)
        return self.get_evidence(tombstone.family_id, tombstone.target_id) is None


class RetentionCoordinator:
    def __init__(
        self,
        repository: LifecycleRepository,
        ledger: TombstoneLedger,
        object_store: ObjectDeletionStore,
    ):
        self.repository = repository
        self.ledger = ledger
        self.object_store = object_store

    def expire(self, now: datetime) -> RetentionResult:
        deleted = 0
        failed = 0
        for evidence in self.repository.expired_evidence(now):
            self.ledger.append(
                evidence.family_id,
                DeletionTarget.EVIDENCE,
                evidence.id,
                now,
                "TTL_EXPIRED",
            )
            self.repository.mark_evidence_inaccessible(evidence.family_id, evidence.id, now)
            try:
                self.object_store.delete(evidence.object_key)
            except Exception:
                failed += 1
                continue
            self.repository.purge_evidence(evidence.family_id, evidence.id)
            deleted += 1
        return RetentionResult(deleted=deleted, failed=failed)


class FamilyPrivacyService:
    def __init__(
        self,
        repository: LifecycleRepository,
        ledger: TombstoneLedger,
        object_store: ObjectDeletionStore,
        revokers: Iterable[FamilyRevoker],
        *,
        clock: Callable[[], datetime] = _utc_now,
    ):
        self.repository = repository
        self.ledger = ledger
        self.object_store = object_store
        self.revokers = tuple(revokers)
        self.clock = clock

    def export(self, scope: FamilyScope) -> bytes:
        if not self.repository.family_exists(scope.family_id):
            raise LookupError("Family data not found")
        records = self.repository.export_records(scope.family_id)
        for record in records:
            forbidden = FORBIDDEN_EXPORT_FIELDS & {str(key).lower() for key in record}
            if forbidden:
                raise ValueError(f"Sensitive export fields are forbidden: {sorted(forbidden)}")
        return json.dumps(
            {"family_id": scope.family_id, "exported_at": self.clock().isoformat(), "records": records},
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode()

    def delete(self, scope: FamilyScope) -> FamilyDeletionResult:
        if not self.repository.family_exists(scope.family_id):
            raise LookupError("Family data not found")
        now = self.clock()
        self.ledger.append(
            scope.family_id,
            DeletionTarget.FAMILY,
            scope.family_id,
            now,
            "REQUESTED",
        )
        self.repository.mark_family_inaccessible(scope.family_id)
        for revoker in self.revokers:
            revoker.revoke_family(scope.family_id)

        failed_objects: list[str] = []
        for evidence in self.repository.family_evidence(scope.family_id):
            self.repository.mark_evidence_inaccessible(scope.family_id, evidence.id, now)
            try:
                self.object_store.delete(evidence.object_key)
            except Exception:
                failed_objects.append(evidence.id)
                continue
            self.repository.purge_evidence(scope.family_id, evidence.id)
        if not failed_objects:
            self.repository.delete_family_rows(scope.family_id)
        return FamilyDeletionResult(
            completed=not failed_objects,
            failed_objects=tuple(failed_objects),
        )


class RestoreReconciler:
    def __init__(self, ledger: TombstoneLedger, restored_repository: LifecycleRepository):
        self.ledger = ledger
        self.restored_repository = restored_repository

    def reconcile_before_access(self, *, backup_watermark: int) -> ReconciliationResult:
        failures: list[str] = []
        last_sequence = backup_watermark
        for tombstone in self.ledger.after(backup_watermark):
            last_sequence = tombstone.sequence
            try:
                if tombstone.target_type == DeletionTarget.FAMILY:
                    self.restored_repository.delete_family_for_restore(tombstone.family_id)
                else:
                    self.restored_repository.delete_evidence_for_restore(
                        tombstone.family_id, tombstone.target_id
                    )
                if not self.restored_repository.is_tombstone_applied(tombstone):
                    failures.append(tombstone.target_id)
            except Exception:
                failures.append(tombstone.target_id)
        return ReconciliationResult(
            safe_to_open=not failures,
            last_sequence=last_sequence,
            failures=tuple(failures),
        )
