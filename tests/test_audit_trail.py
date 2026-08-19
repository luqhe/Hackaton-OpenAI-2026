from __future__ import annotations

from dataclasses import asdict, fields, replace
from datetime import UTC, datetime

import pytest

from api.data_security.audit import (
    AuditAction,
    AuditActorType,
    AuditInput,
    AuditKeyring,
    AuditResult,
    AuditTargetType,
    AuditTrail,
    InMemoryAuditRepository,
)
from guardian_core.config import Environment

NOW = datetime(2026, 8, 19, 12, tzinfo=UTC)


def _input(action: AuditAction = AuditAction.EVIDENCE_ACCESSED) -> AuditInput:
    return AuditInput(
        family_id="family-1",
        actor_type=AuditActorType.ACCOUNT,
        actor_id="account-1",
        action=action,
        target_type=AuditTargetType.EVIDENCE,
        target_id="evidence-1",
        result=AuditResult.SUCCESS,
        correlation_id="correlation-1",
    )


def _trail():
    repository = InMemoryAuditRepository()
    keyring = AuditKeyring(
        current_key_id="audit-v1",
        keys={"audit-v1": b"a" * 32},
        environment=Environment.TEST,
    )
    trail = AuditTrail(repository, keyring, clock=lambda: NOW)
    return trail, repository, keyring


def test_audit_chain_verifies_across_key_rotation() -> None:
    trail, _, keyring = _trail()
    first = trail.append(_input())
    keyring.rotate("audit-v2", b"b" * 32)
    second = trail.append(_input(AuditAction.POLICY_UPDATED))

    verification = trail.verify()

    assert second.previous_hash == first.event_hash
    assert first.key_id == "audit-v1"
    assert second.key_id == "audit-v2"
    assert verification.valid is True
    assert verification.checked_records == 2


@pytest.mark.parametrize("mutation", ["edit", "remove", "reorder"])
def test_audit_verifier_detects_non_terminal_tampering(mutation: str) -> None:
    trail, repository, _ = _trail()
    trail.append(_input())
    trail.append(_input(AuditAction.POLICY_UPDATED))
    trail.append(_input(AuditAction.INCIDENT_DECIDED))

    if mutation == "edit":
        repository.records[0] = replace(repository.records[0], target_id="changed")
    elif mutation == "remove":
        repository.records.pop(1)
    else:
        repository.records[0], repository.records[1] = repository.records[1], repository.records[0]

    assert trail.verify().valid is False


def test_checkpoint_detects_terminal_truncation() -> None:
    trail, repository, _ = _trail()
    trail.append(_input())
    trail.append(_input(AuditAction.POLICY_UPDATED))
    checkpoint = trail.checkpoint()
    repository.records.pop()

    assert trail.verify(checkpoint=checkpoint).valid is False


def test_audit_input_has_no_free_form_or_sensitive_content_field() -> None:
    names = {field.name for field in fields(AuditInput)}

    assert names == {
        "family_id",
        "actor_type",
        "actor_id",
        "action",
        "target_type",
        "target_id",
        "result",
        "correlation_id",
    }
    with pytest.raises(TypeError):
        AuditInput(**asdict(_input()), ocr="sensitive")


def test_managed_environment_rejects_default_or_short_audit_secrets() -> None:
    for secret in (b"", b"development-only", b"short"):
        with pytest.raises(ValueError, match="audit HMAC"):
            AuditKeyring(
                current_key_id="audit-v1",
                keys={"audit-v1": secret},
                environment=Environment.PRODUCTION,
            )
