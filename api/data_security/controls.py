from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from api.data_security.config import DataSecuritySettings


class EvidenceState(StrEnum):
    LOCAL_IMPLEMENTED = "LOCAL_IMPLEMENTED"
    EXTERNAL_PENDING = "EXTERNAL_PENDING"


@dataclass(frozen=True, slots=True)
class RoadmapEvidence:
    state: EvidenceState
    local_evidence: str
    external_evidence: str


@dataclass(frozen=True, slots=True)
class SecurityControlReport:
    configuration_valid: bool
    local_controls: tuple[str, ...]
    external_pending: tuple[str, ...]


ROADMAP_EVIDENCE = {
    "R2-13": RoadmapEvidence(
        EvidenceState.EXTERNAL_PENDING,
        "PostgreSQL pool adapter and environment gate; SQLite local-only",
        "Managed PostgreSQL connectivity, pooling, TLS and least-privilege evidence in staging",
    ),
    "R2-14": RoadmapEvidence(
        EvidenceState.EXTERNAL_PENDING,
        "Versioned manifest, checksum drift detection, up/down and non-empty rollback guard",
        "Empty and representative-copy migration plus rollback/forward-fix exercise in staging",
    ),
    "R2-15": RoadmapEvidence(
        EvidenceState.EXTERNAL_PENDING,
        "Private filesystem adapter for local tests and injected S3-compatible SSE-KMS adapter",
        "Provider bucket public-access block, IAM and object lifecycle attestation",
    ),
    "R2-16": RoadmapEvidence(
        EvidenceState.EXTERNAL_PENDING,
        "Config rejects plaintext DB/object endpoints and missing KMS/audit key material",
        "Provider TLS, encryption-at-rest, KMS policy and rotation evidence",
    ),
    "R2-17": RoadmapEvidence(
        EvidenceState.EXTERNAL_PENDING,
        "Five-minute-max grants bind family, account session and revocation epoch",
        "Deployed auth route integration and logout/revocation exercise in staging",
    ),
    "R2-18": RoadmapEvidence(
        EvidenceState.EXTERNAL_PENDING,
        "Clock-driven TTL coordinator closes access, tombstones, retries and deletes blobs",
        "Scheduled job, alerts and provider lifecycle reconciliation in staging",
    ),
    "R2-19": RoadmapEvidence(
        EvidenceState.EXTERNAL_PENDING,
        "Family-scoped minimized export and tombstone-first revocation/deletion coordinator",
        "Full repository wiring, reauthentication UI and end-to-end family deletion",
    ),
    "R2-20": RoadmapEvidence(
        EvidenceState.EXTERNAL_PENDING,
        "Restore reconciler reapplies monotonic tombstones before access can open",
        "Encrypted managed backup restore with RPO/RTO and no-resurrection proof",
    ),
    "R2-24": RoadmapEvidence(
        EvidenceState.EXTERNAL_PENDING,
        "Closed metadata-only audit schema and policy/evidence/decision action vocabulary",
        "Instrumentation of all integrated routes and least-privilege audit query in staging",
    ),
    "R2-25": RoadmapEvidence(
        EvidenceState.EXTERNAL_PENDING,
        "Append-only SQL triggers, HMAC chain, key IDs, rotation and checkpoint verifier",
        "External immutable checkpoint/WORM control, restore and break-glass exercise",
    ),
    "R2-26": RoadmapEvidence(
        EvidenceState.EXTERNAL_PENDING,
        "Atomic limiter with HMAC identities and separate unlock/ack/heartbeat buckets",
        "Auth middleware wiring and distributed PostgreSQL-backed load/abuse test",
    ),
}

EXTERNAL_CONTROL_GATES = (
    "managed-postgresql-tls-and-at-rest-attestation",
    "kms-key-policy-and-rotation-exercise",
    "private-bucket-public-access-block-attestation",
    "representative-migration-and-safe-rollback-in-staging",
    "encrypted-backup-restore-with-tombstone-reconciliation",
    "external-immutable-audit-checkpoint",
    "distributed-rate-limit-load-test",
)


def security_control_report(settings: DataSecuritySettings) -> SecurityControlReport:
    settings.database.validate()
    settings.validate()
    return SecurityControlReport(
        configuration_valid=True,
        local_controls=(
            "database-environment-gate",
            "postgres-verified-tls-config",
            "private-object-store-config",
            "kms-key-id-config",
            "audit-hmac-key-id-and-secret",
            "short-lived-evidence-grants",
            "rate-limit-identity-hmac",
        ),
        external_pending=EXTERNAL_CONTROL_GATES,
    )
