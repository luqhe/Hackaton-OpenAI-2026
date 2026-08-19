from __future__ import annotations

from pathlib import Path

import pytest

from api.data_security.config import DataSecuritySettings
from api.data_security.controls import ROADMAP_EVIDENCE, EvidenceState, security_control_report

PROJECT_ROOT = Path(__file__).resolve().parents[1]
ASSIGNED_IDS = {
    *(f"R2-{item:02d}" for item in range(13, 21)),
    *(f"R2-{item:02d}" for item in range(24, 27)),
}


def _read_env(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in path.read_text().splitlines():
        stripped = line.strip()
        if stripped and not stripped.startswith("#"):
            name, value = stripped.split("=", 1)
            values[name] = value
    return values


def _managed_env() -> dict[str, str]:
    return {
        "GUARDIAN_ENVIRONMENT": "staging",
        "GUARDIAN_DATABASE_URL": ("postgresql://guardian:secret@db.internal/guardian?sslmode=verify-full"),
        "GUARDIAN_DATABASE_POOL_MIN": "1",
        "GUARDIAN_DATABASE_POOL_MAX": "8",
        "GUARDIAN_OBJECT_STORE_PROVIDER": "s3",
        "GUARDIAN_OBJECT_STORE_BUCKET": "guardian-private-staging",
        "GUARDIAN_OBJECT_STORE_ENDPOINT": "https://objects.internal",
        "GUARDIAN_KMS_KEY_ID": "kms-staging-123",
        "GUARDIAN_AUDIT_HMAC_KEY_ID": "audit-staging-v1",
        "GUARDIAN_AUDIT_HMAC_SECRET": "a" * 32,
        "GUARDIAN_RATE_LIMIT_HMAC_SECRET": "r" * 32,
        "GUARDIAN_EVIDENCE_GRANT_TTL_SECONDS": "120",
    }


def test_development_example_is_locally_runnable() -> None:
    values = _read_env(PROJECT_ROOT / "config/environments/development.env.example")

    settings = DataSecuritySettings.from_env(values)

    assert settings.object_store_provider == "filesystem"
    assert settings.evidence_grant_ttl_seconds == 120


@pytest.mark.parametrize("environment", ["staging", "production"])
def test_managed_examples_are_non_deployable_placeholders(environment: str) -> None:
    values = _read_env(PROJECT_ROOT / f"config/environments/{environment}.env.example")

    with pytest.raises(ValueError, match="placeholder"):
        DataSecuritySettings.from_env(values)


def test_managed_controls_validate_locally_but_provider_proof_stays_pending() -> None:
    settings = DataSecuritySettings.from_env(_managed_env())

    report = security_control_report(settings)

    assert report.configuration_valid is True
    assert report.external_pending == (
        "managed-postgresql-tls-and-at-rest-attestation",
        "kms-key-policy-and-rotation-exercise",
        "private-bucket-public-access-block-attestation",
        "representative-migration-and-safe-rollback-in-staging",
        "encrypted-backup-restore-with-tombstone-reconciliation",
        "external-immutable-audit-checkpoint",
        "distributed-rate-limit-load-test",
    )


def test_roadmap_evidence_manifest_is_complete_and_never_marks_external_work_done() -> None:
    assert set(ROADMAP_EVIDENCE) == ASSIGNED_IDS
    assert all(item.local_evidence for item in ROADMAP_EVIDENCE.values())
    externally_gated = {
        roadmap_id
        for roadmap_id, item in ROADMAP_EVIDENCE.items()
        if item.state == EvidenceState.EXTERNAL_PENDING
    }
    assert externally_gated == {
        "R2-13",
        "R2-14",
        "R2-15",
        "R2-16",
        "R2-17",
        "R2-18",
        "R2-19",
        "R2-20",
        "R2-24",
        "R2-25",
        "R2-26",
    }
