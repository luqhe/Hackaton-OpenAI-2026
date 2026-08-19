from __future__ import annotations

import sqlite3
from dataclasses import replace

import pytest

from api.data_security.migrations import (
    MigrationRunner,
    SchemaDriftError,
    SQLiteMigrationSession,
    UnsafeRollbackError,
)
from api.data_security.schema import DATA_SECURITY_MIGRATION_ID, data_security_migration


@pytest.fixture
def connection() -> sqlite3.Connection:
    database = sqlite3.connect(":memory:")
    database.row_factory = sqlite3.Row
    database.execute("PRAGMA foreign_keys = ON")
    database.executescript(
        """
        CREATE TABLE families (
            id TEXT PRIMARY KEY
        );
        CREATE TABLE incidents (
            family_id TEXT NOT NULL,
            id TEXT NOT NULL,
            PRIMARY KEY (family_id, id),
            FOREIGN KEY (family_id) REFERENCES families(id)
        );
        INSERT INTO families(id) VALUES ('family-1'), ('family-2');
        INSERT INTO incidents(family_id, id) VALUES ('family-1', 'incident-1');
        """
    )
    database.commit()
    try:
        yield database
    finally:
        database.close()


def _runner(connection: sqlite3.Connection) -> MigrationRunner:
    return MigrationRunner(
        SQLiteMigrationSession(connection),
        [data_security_migration("sqlite")],
    )


def _table_names(connection: sqlite3.Connection) -> set[str]:
    return {
        row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall()
    }


def test_migration_round_trip_on_empty_additive_tables(connection: sqlite3.Connection) -> None:
    runner = _runner(connection)

    runner.up()

    assert runner.applied_ids() == [DATA_SECURITY_MIGRATION_ID]
    assert {
        "evidence_objects",
        "evidence_access_grants",
        "deletion_tombstones",
        "audit_events",
        "audit_checkpoints",
        "rate_limit_windows",
    }.issubset(_table_names(connection))

    runner.down(DATA_SECURITY_MIGRATION_ID)

    assert runner.applied_ids() == []
    assert "evidence_objects" not in _table_names(connection)
    assert "deletion_tombstones" not in _table_names(connection)


def test_migration_is_idempotent_and_detects_manifest_drift(connection: sqlite3.Connection) -> None:
    runner = _runner(connection)
    runner.up()
    runner.up()
    assert runner.applied_ids() == [DATA_SECURITY_MIGRATION_ID]

    original = data_security_migration("sqlite")
    changed = replace(original, description="changed after deployment")
    drifted_runner = MigrationRunner(SQLiteMigrationSession(connection), [changed])

    with pytest.raises(SchemaDriftError, match=DATA_SECURITY_MIGRATION_ID):
        drifted_runner.up()


def test_composite_foreign_key_rejects_cross_family_evidence(
    connection: sqlite3.Connection,
) -> None:
    _runner(connection).up()

    with pytest.raises(sqlite3.IntegrityError):
        connection.execute(
            """
            INSERT INTO evidence_objects(
                family_id, id, incident_id, object_key, content_type, sha256,
                size_bytes, created_at, expires_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "family-2",
                "evidence-1",
                "incident-1",
                "obj-opaque",
                "text/plain",
                "a" * 64,
                7,
                "2026-08-19T12:00:00+00:00",
                "2026-09-18T12:00:00+00:00",
            ),
        )


def test_audit_rows_are_append_only_in_sqlite(connection: sqlite3.Connection) -> None:
    _runner(connection).up()
    connection.execute(
        """
        INSERT INTO audit_events(
            event_id, family_id, occurred_at, actor_type, actor_id, action,
            target_type, target_id, result, correlation_id, key_id,
            previous_hash, event_hash
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "audit-1",
            "family-1",
            "2026-08-19T12:00:00+00:00",
            "ACCOUNT",
            "account-1",
            "POLICY_UPDATED",
            "POLICY",
            "policy-1",
            "SUCCESS",
            "correlation-1",
            "audit-v1",
            "0" * 64,
            "1" * 64,
        ),
    )

    with pytest.raises(sqlite3.IntegrityError, match="append-only"):
        connection.execute("UPDATE audit_events SET target_id = 'changed' WHERE event_id = 'audit-1'")
    with pytest.raises(sqlite3.IntegrityError, match="append-only"):
        connection.execute("DELETE FROM audit_events WHERE event_id = 'audit-1'")


def test_rollback_refuses_to_drop_existing_tombstone(connection: sqlite3.Connection) -> None:
    runner = _runner(connection)
    runner.up()
    connection.execute(
        """
        INSERT INTO deletion_tombstones(
            family_id, target_type, target_id, deleted_at, reason
        ) VALUES (?, ?, ?, ?, ?)
        """,
        (
            "family-1",
            "FAMILY",
            "family-1",
            "2026-08-19T12:00:00+00:00",
            "REQUESTED",
        ),
    )
    connection.commit()

    with pytest.raises(UnsafeRollbackError, match="deletion_tombstones"):
        runner.down(DATA_SECURITY_MIGRATION_ID)

    assert "deletion_tombstones" in _table_names(connection)
    assert runner.applied_ids() == [DATA_SECURITY_MIGRATION_ID]


def test_postgres_manifest_uses_family_keys_and_append_only_triggers() -> None:
    migration = data_security_migration("postgresql")
    emitted_sql = "\n".join(migration.up_statements)

    assert "FOREIGN KEY (family_id, incident_id)" in emitted_sql
    assert "FOREIGN KEY (family_id, evidence_id)" in emitted_sql
    assert "CREATE TRIGGER audit_events_no_update" in emitted_sql
    assert "CREATE TRIGGER audit_events_no_delete" in emitted_sql
    assert migration.phase.value == "EXPAND"
