from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

from api.data_security.evidence import EvidenceRecord
from api.data_security.lifecycle import (
    DeletionTarget,
    FamilyPrivacyService,
    InMemoryLifecycleRepository,
    InMemoryRevoker,
    InMemoryTombstoneLedger,
    RestoreReconciler,
    RetentionCoordinator,
)
from guardian_core.identity import FamilyScope, MembershipRole

NOW = datetime(2026, 8, 19, 12, tzinfo=UTC)


class _ObjectStore:
    def __init__(self) -> None:
        self.objects = {"evidence/object-1": b"minimal"}
        self.fail_next_delete = False
        self.calls: list[tuple[str, str]] = []

    def delete(self, object_key: str) -> None:
        self.calls.append(("delete_blob", object_key))
        if self.fail_next_delete:
            self.fail_next_delete = False
            raise RuntimeError("object storage unavailable")
        self.objects.pop(object_key, None)


def _scope(family_id: str = "family-1") -> FamilyScope:
    return FamilyScope("account-1", family_id, "membership-1", MembershipRole.OWNER)


def _expired_evidence() -> EvidenceRecord:
    return EvidenceRecord(
        family_id="family-1",
        id="evidence-1",
        incident_id="incident-1",
        object_key="evidence/object-1",
        content_type="text/plain",
        sha256="a" * 64,
        size_bytes=7,
        created_at=NOW - timedelta(days=31),
        expires_at=NOW - timedelta(seconds=1),
    )


def test_retention_writes_tombstone_and_closes_access_before_blob_delete() -> None:
    calls: list[tuple[str, str]] = []
    ledger = InMemoryTombstoneLedger(call_log=calls)
    repository = InMemoryLifecycleRepository(call_log=calls)
    repository.add_evidence(_expired_evidence())
    objects = _ObjectStore()
    coordinator = RetentionCoordinator(repository, ledger, objects)

    result = coordinator.expire(NOW)

    assert result.deleted == 1
    assert calls[:2] == [("tombstone", "evidence-1"), ("inaccessible", "evidence-1")]
    assert objects.calls == [("delete_blob", "evidence/object-1")]
    assert repository.get_evidence("family-1", "evidence-1") is None


def test_retention_failure_stays_inaccessible_and_retries_idempotently() -> None:
    ledger = InMemoryTombstoneLedger()
    repository = InMemoryLifecycleRepository()
    repository.add_evidence(_expired_evidence())
    objects = _ObjectStore()
    objects.fail_next_delete = True
    coordinator = RetentionCoordinator(repository, ledger, objects)

    first = coordinator.expire(NOW)
    second = coordinator.expire(NOW + timedelta(minutes=1))

    assert first.failed == 1
    assert second.deleted == 1
    assert len(ledger.all()) == 1
    assert repository.is_evidence_accessible("family-1", "evidence-1") is False


def test_family_export_is_scoped_and_rejects_sensitive_fields() -> None:
    repository = InMemoryLifecycleRepository()
    repository.register_family(
        "family-1",
        records=[
            {"record_type": "POLICY", "record_id": "policy-1", "action": "ALERT"},
            {"record_type": "EVIDENCE", "record_id": "evidence-1", "content_type": "text/plain"},
        ],
    )
    privacy = FamilyPrivacyService(
        repository,
        InMemoryTombstoneLedger(),
        _ObjectStore(),
        [InMemoryRevoker()],
        clock=lambda: NOW,
    )

    exported = json.loads(privacy.export(_scope()))

    assert exported["family_id"] == "family-1"
    assert exported["records"][0]["action"] == "ALERT"
    assert "object_key" not in privacy.export(_scope()).decode()

    repository.register_family(
        "family-sensitive",
        records=[{"record_type": "EVIDENCE", "record_id": "evidence-2", "ocr": "secret"}],
    )
    try:
        privacy.export(_scope("family-sensitive"))
    except ValueError as error:
        assert "sensitive" in str(error).lower()
    else:
        raise AssertionError("Sensitive export field was accepted")


def test_family_delete_revokes_access_before_removing_rows() -> None:
    calls: list[tuple[str, str]] = []
    repository = InMemoryLifecycleRepository(call_log=calls)
    repository.register_family("family-1", records=[])
    repository.add_evidence(_expired_evidence())
    ledger = InMemoryTombstoneLedger(call_log=calls)
    revokers = [InMemoryRevoker(call_log=calls) for _ in range(3)]
    privacy = FamilyPrivacyService(
        repository,
        ledger,
        _ObjectStore(),
        revokers,
        clock=lambda: NOW,
    )

    result = privacy.delete(_scope())

    assert result.completed is True
    assert calls[0] == ("tombstone", "family-1")
    assert calls[1] == ("family_inaccessible", "family-1")
    assert [call for call in calls if call[0] == "revoke"] == [
        ("revoke", "family-1"),
        ("revoke", "family-1"),
        ("revoke", "family-1"),
    ]
    assert calls[-1] == ("delete_rows", "family-1")


def test_restore_reconciliation_reapplies_tombstones_before_access() -> None:
    ledger = InMemoryTombstoneLedger()
    ledger.append("family-deleted", DeletionTarget.FAMILY, "family-deleted", NOW, "REQUESTED")
    ledger.append("family-1", DeletionTarget.EVIDENCE, "evidence-1", NOW, "TTL_EXPIRED")
    restored = InMemoryLifecycleRepository()
    restored.register_family("family-deleted", records=[])
    restored.register_family("family-1", records=[])
    restored.add_evidence(_expired_evidence())

    result = RestoreReconciler(ledger, restored).reconcile_before_access(backup_watermark=0)

    assert result.safe_to_open is True
    assert restored.family_exists("family-deleted") is False
    assert restored.get_evidence("family-1", "evidence-1") is None
    assert result.last_sequence == 2
