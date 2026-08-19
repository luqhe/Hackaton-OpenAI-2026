from __future__ import annotations

from api.data_security.migrations import Migration, MigrationPhase, MigrationRisk

DATA_SECURITY_MIGRATION_ID = "r2_data_security_001"

MANAGED_TABLES = (
    "evidence_access_grants",
    "evidence_objects",
    "audit_checkpoints",
    "audit_events",
    "rate_limit_windows",
    "deletion_tombstones",
)


def data_security_migration(dialect: str) -> Migration:
    if dialect == "sqlite":
        up_statements = _SQLITE_UP
        down_statements = _SQLITE_DOWN
    elif dialect in {"postgres", "postgresql", "postgresql+psycopg"}:
        up_statements = _POSTGRES_UP
        down_statements = _POSTGRES_DOWN
    else:
        raise ValueError(f"Unsupported migration dialect: {dialect}")
    return Migration(
        identifier=DATA_SECURITY_MIGRATION_ID,
        description="Add private evidence, deletion, audit, and abuse-control tables",
        phase=MigrationPhase.EXPAND,
        risk=MigrationRisk.LOW,
        depends_on=(),
        up_statements=up_statements,
        down_statements=down_statements,
        non_empty_down_guards=MANAGED_TABLES,
    )


_SQLITE_UP = (
    """
    CREATE TABLE evidence_objects (
        family_id TEXT NOT NULL,
        id TEXT NOT NULL,
        incident_id TEXT NOT NULL,
        object_key TEXT NOT NULL UNIQUE,
        content_type TEXT NOT NULL,
        sha256 TEXT NOT NULL CHECK (length(sha256) = 64),
        size_bytes INTEGER NOT NULL CHECK (size_bytes > 0),
        created_at TEXT NOT NULL,
        expires_at TEXT NOT NULL,
        deleted_at TEXT,
        PRIMARY KEY (family_id, id),
        FOREIGN KEY (family_id) REFERENCES families(id),
        FOREIGN KEY (family_id, incident_id) REFERENCES incidents(family_id, id)
    )
    """,
    """
    CREATE TABLE evidence_access_grants (
        family_id TEXT NOT NULL,
        id TEXT NOT NULL,
        evidence_id TEXT NOT NULL,
        token_digest TEXT NOT NULL UNIQUE CHECK (length(token_digest) = 64),
        principal_id TEXT NOT NULL,
        session_id TEXT NOT NULL,
        revocation_epoch INTEGER NOT NULL CHECK (revocation_epoch >= 0),
        created_at TEXT NOT NULL,
        expires_at TEXT NOT NULL,
        revoked_at TEXT,
        PRIMARY KEY (family_id, id),
        FOREIGN KEY (family_id, evidence_id)
            REFERENCES evidence_objects(family_id, id) ON DELETE CASCADE
    )
    """,
    """
    CREATE TABLE deletion_tombstones (
        sequence INTEGER PRIMARY KEY AUTOINCREMENT,
        family_id TEXT NOT NULL,
        target_type TEXT NOT NULL,
        target_id TEXT NOT NULL,
        deleted_at TEXT NOT NULL,
        reason TEXT NOT NULL,
        UNIQUE (family_id, target_type, target_id)
    )
    """,
    """
    CREATE TABLE audit_events (
        sequence INTEGER PRIMARY KEY AUTOINCREMENT,
        event_id TEXT NOT NULL UNIQUE,
        family_id TEXT NOT NULL,
        occurred_at TEXT NOT NULL,
        actor_type TEXT NOT NULL,
        actor_id TEXT NOT NULL,
        action TEXT NOT NULL,
        target_type TEXT NOT NULL,
        target_id TEXT NOT NULL,
        result TEXT NOT NULL,
        correlation_id TEXT NOT NULL,
        key_id TEXT NOT NULL,
        previous_hash TEXT NOT NULL CHECK (length(previous_hash) = 64),
        event_hash TEXT NOT NULL CHECK (length(event_hash) = 64)
    )
    """,
    """
    CREATE TRIGGER audit_events_no_update
    BEFORE UPDATE ON audit_events
    BEGIN
        SELECT RAISE(ABORT, 'audit_events is append-only');
    END
    """,
    """
    CREATE TRIGGER audit_events_no_delete
    BEFORE DELETE ON audit_events
    BEGIN
        SELECT RAISE(ABORT, 'audit_events is append-only');
    END
    """,
    """
    CREATE TABLE audit_checkpoints (
        sequence INTEGER PRIMARY KEY,
        event_hash TEXT NOT NULL CHECK (length(event_hash) = 64),
        key_id TEXT NOT NULL,
        checkpoint_hash TEXT NOT NULL CHECK (length(checkpoint_hash) = 64),
        created_at TEXT NOT NULL
    )
    """,
    """
    CREATE TRIGGER audit_checkpoints_no_update
    BEFORE UPDATE ON audit_checkpoints
    BEGIN
        SELECT RAISE(ABORT, 'audit_checkpoints is append-only');
    END
    """,
    """
    CREATE TRIGGER audit_checkpoints_no_delete
    BEFORE DELETE ON audit_checkpoints
    BEGIN
        SELECT RAISE(ABORT, 'audit_checkpoints is append-only');
    END
    """,
    """
    CREATE TABLE rate_limit_windows (
        bucket_key TEXT NOT NULL CHECK (length(bucket_key) = 64),
        route_class TEXT NOT NULL,
        window_started_at TEXT NOT NULL,
        request_count INTEGER NOT NULL CHECK (request_count >= 0),
        expires_at TEXT NOT NULL,
        PRIMARY KEY (bucket_key, route_class, window_started_at)
    )
    """,
    "CREATE INDEX idx_evidence_objects_expiry ON evidence_objects(expires_at) WHERE deleted_at IS NULL",
    "CREATE INDEX idx_evidence_grants_expiry ON evidence_access_grants(expires_at) WHERE revoked_at IS NULL",
    "CREATE INDEX idx_tombstones_family_sequence ON deletion_tombstones(family_id, sequence)",
    "CREATE INDEX idx_audit_family_sequence ON audit_events(family_id, sequence)",
    "CREATE INDEX idx_rate_limit_expiry ON rate_limit_windows(expires_at)",
)

_SQLITE_DOWN = (
    "DROP TABLE rate_limit_windows",
    "DROP TABLE audit_checkpoints",
    "DROP TABLE audit_events",
    "DROP TABLE evidence_access_grants",
    "DROP TABLE evidence_objects",
    "DROP TABLE deletion_tombstones",
)

_POSTGRES_UP = (
    """
    CREATE TABLE evidence_objects (
        family_id TEXT NOT NULL,
        id TEXT NOT NULL,
        incident_id TEXT NOT NULL,
        object_key TEXT NOT NULL UNIQUE,
        content_type TEXT NOT NULL,
        sha256 CHAR(64) NOT NULL,
        size_bytes BIGINT NOT NULL CHECK (size_bytes > 0),
        created_at TIMESTAMPTZ NOT NULL,
        expires_at TIMESTAMPTZ NOT NULL,
        deleted_at TIMESTAMPTZ,
        PRIMARY KEY (family_id, id),
        FOREIGN KEY (family_id) REFERENCES families(id),
        FOREIGN KEY (family_id, incident_id) REFERENCES incidents(family_id, id)
    )
    """,
    """
    CREATE TABLE evidence_access_grants (
        family_id TEXT NOT NULL,
        id TEXT NOT NULL,
        evidence_id TEXT NOT NULL,
        token_digest CHAR(64) NOT NULL UNIQUE,
        principal_id TEXT NOT NULL,
        session_id TEXT NOT NULL,
        revocation_epoch BIGINT NOT NULL CHECK (revocation_epoch >= 0),
        created_at TIMESTAMPTZ NOT NULL,
        expires_at TIMESTAMPTZ NOT NULL,
        revoked_at TIMESTAMPTZ,
        PRIMARY KEY (family_id, id),
        FOREIGN KEY (family_id, evidence_id)
            REFERENCES evidence_objects(family_id, id) ON DELETE CASCADE
    )
    """,
    """
    CREATE TABLE deletion_tombstones (
        sequence BIGSERIAL PRIMARY KEY,
        family_id TEXT NOT NULL,
        target_type TEXT NOT NULL,
        target_id TEXT NOT NULL,
        deleted_at TIMESTAMPTZ NOT NULL,
        reason TEXT NOT NULL,
        UNIQUE (family_id, target_type, target_id)
    )
    """,
    """
    CREATE TABLE audit_events (
        sequence BIGSERIAL PRIMARY KEY,
        event_id TEXT NOT NULL UNIQUE,
        family_id TEXT NOT NULL,
        occurred_at TIMESTAMPTZ NOT NULL,
        actor_type TEXT NOT NULL,
        actor_id TEXT NOT NULL,
        action TEXT NOT NULL,
        target_type TEXT NOT NULL,
        target_id TEXT NOT NULL,
        result TEXT NOT NULL,
        correlation_id TEXT NOT NULL,
        key_id TEXT NOT NULL,
        previous_hash CHAR(64) NOT NULL,
        event_hash CHAR(64) NOT NULL
    )
    """,
    """
    CREATE TABLE audit_checkpoints (
        sequence BIGINT PRIMARY KEY REFERENCES audit_events(sequence),
        event_hash CHAR(64) NOT NULL,
        key_id TEXT NOT NULL,
        checkpoint_hash CHAR(64) NOT NULL,
        created_at TIMESTAMPTZ NOT NULL
    )
    """,
    """
    CREATE OR REPLACE FUNCTION guardian_reject_audit_mutation()
    RETURNS trigger LANGUAGE plpgsql AS $$
    BEGIN
        RAISE EXCEPTION 'Guardian audit records are append-only';
    END;
    $$
    """,
    """
    CREATE TRIGGER audit_events_no_update
    BEFORE UPDATE ON audit_events
    FOR EACH ROW EXECUTE FUNCTION guardian_reject_audit_mutation()
    """,
    """
    CREATE TRIGGER audit_events_no_delete
    BEFORE DELETE ON audit_events
    FOR EACH ROW EXECUTE FUNCTION guardian_reject_audit_mutation()
    """,
    """
    CREATE TRIGGER audit_checkpoints_no_update
    BEFORE UPDATE ON audit_checkpoints
    FOR EACH ROW EXECUTE FUNCTION guardian_reject_audit_mutation()
    """,
    """
    CREATE TRIGGER audit_checkpoints_no_delete
    BEFORE DELETE ON audit_checkpoints
    FOR EACH ROW EXECUTE FUNCTION guardian_reject_audit_mutation()
    """,
    """
    CREATE TABLE rate_limit_windows (
        bucket_key CHAR(64) NOT NULL,
        route_class TEXT NOT NULL,
        window_started_at TIMESTAMPTZ NOT NULL,
        request_count INTEGER NOT NULL CHECK (request_count >= 0),
        expires_at TIMESTAMPTZ NOT NULL,
        PRIMARY KEY (bucket_key, route_class, window_started_at)
    )
    """,
    "CREATE INDEX idx_evidence_objects_expiry ON evidence_objects(expires_at) WHERE deleted_at IS NULL",
    "CREATE INDEX idx_evidence_grants_expiry ON evidence_access_grants(expires_at) WHERE revoked_at IS NULL",
    "CREATE INDEX idx_tombstones_family_sequence ON deletion_tombstones(family_id, sequence)",
    "CREATE INDEX idx_audit_family_sequence ON audit_events(family_id, sequence)",
    "CREATE INDEX idx_rate_limit_expiry ON rate_limit_windows(expires_at)",
)

_POSTGRES_DOWN = (
    "DROP TABLE rate_limit_windows",
    "DROP TABLE audit_checkpoints",
    "DROP TABLE audit_events",
    "DROP FUNCTION guardian_reject_audit_mutation()",
    "DROP TABLE evidence_access_grants",
    "DROP TABLE evidence_objects",
    "DROP TABLE deletion_tombstones",
)
