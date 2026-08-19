from __future__ import annotations

import hashlib
import json
import sqlite3
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

from guardian_core.config import Environment
from guardian_core.identity import (
    Account,
    AccountStatus,
    Child,
    DeviceLifecycleStatus,
    Family,
    FamilyScope,
    FamilyStatus,
    Membership,
    MembershipRole,
    MembershipStatus,
)
from guardian_core.models import (
    CommandStatus,
    CommandType,
    DailyAppUsage,
    DailyReport,
    Device,
    DeviceCommand,
    DeviceHeartbeat,
    DevicePairRequest,
    EnforcementAction,
    FamilyDeletionCounts,
    FamilyDeletionReceipt,
    FamilyDeletionStatus,
    Incident,
    IncidentCreate,
    IncidentStatus,
    PilotFunnelStageMetric,
    PilotMetricsReport,
    PilotOnboardingEvent,
    PilotOnboardingEventCreate,
    PilotOnboardingStage,
    PolicyAction,
    PolicyRule,
    RiskCategory,
    RiskLevel,
    TelemetryUpdate,
)
from guardian_core.pilot import PilotTechnicalTelemetry
from guardian_core.version import SCHEMA_VERSION

HEARTBEAT_STALE_AFTER = timedelta(minutes=2)


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


TABLE_SCHEMA = """
CREATE TABLE IF NOT EXISTS accounts (
    id TEXT PRIMARY KEY,
    email TEXT NOT NULL COLLATE NOCASE UNIQUE,
    password_hash TEXT,
    auth_enabled INTEGER NOT NULL DEFAULT 1 CHECK (auth_enabled IN (0, 1)),
    status TEXT NOT NULL DEFAULT 'ACTIVE' CHECK (status IN ('ACTIVE', 'DISABLED')),
    created_at TEXT NOT NULL,
    disabled_at TEXT,
    CHECK (
        (auth_enabled = 0 AND password_hash IS NULL)
        OR (auth_enabled = 1 AND password_hash IS NOT NULL)
    )
);

CREATE TABLE IF NOT EXISTS families (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL CHECK (length(name) BETWEEN 1 AND 120),
    status TEXT NOT NULL DEFAULT 'ACTIVE'
        CHECK (status IN ('ACTIVE', 'DELETION_PENDING')),
    created_at TEXT NOT NULL,
    deletion_requested_at TEXT
);

CREATE TABLE IF NOT EXISTS memberships (
    id TEXT PRIMARY KEY,
    account_id TEXT NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
    family_id TEXT NOT NULL REFERENCES families(id) ON DELETE CASCADE,
    role TEXT NOT NULL CHECK (role IN ('OWNER', 'GUARDIAN')),
    status TEXT NOT NULL CHECK (status IN ('ACTIVE', 'REVOKED')),
    created_at TEXT NOT NULL,
    revoked_at TEXT,
    UNIQUE(account_id, family_id),
    UNIQUE(family_id, id),
    UNIQUE(account_id, family_id, id)
);

CREATE TABLE IF NOT EXISTS children (
    id TEXT PRIMARY KEY,
    family_id TEXT NOT NULL REFERENCES families(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE(family_id, id)
);

CREATE TABLE IF NOT EXISTS devices (
    id TEXT PRIMARY KEY,
    family_id TEXT NOT NULL,
    child_id TEXT NOT NULL,
    name TEXT NOT NULL,
    platform TEXT NOT NULL,
    paired_at TEXT NOT NULL,
    last_seen_at TEXT,
    lifecycle_status TEXT NOT NULL DEFAULT 'ACTIVE'
        CHECK (lifecycle_status IN ('ACTIVE', 'REVOKED')),
    protection_status TEXT NOT NULL DEFAULT 'DEGRADED'
        CHECK (protection_status IN ('PROTECTED', 'DEGRADED')),
    UNIQUE(family_id, id),
    UNIQUE(family_id, child_id, id),
    FOREIGN KEY (family_id, child_id)
        REFERENCES children(family_id, id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS policies (
    family_id TEXT NOT NULL,
    child_id TEXT NOT NULL,
    category TEXT NOT NULL,
    action TEXT NOT NULL,
    minimum_risk TEXT NOT NULL,
    minimum_confidence REAL NOT NULL,
    PRIMARY KEY (family_id, child_id, category),
    FOREIGN KEY (family_id, child_id)
        REFERENCES children(family_id, id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS incidents (
    id TEXT PRIMARY KEY,
    family_id TEXT NOT NULL,
    child_id TEXT NOT NULL,
    device_id TEXT NOT NULL,
    application TEXT NOT NULL,
    occurred_at TEXT NOT NULL,
    category TEXT NOT NULL,
    direction TEXT NOT NULL,
    severity TEXT NOT NULL,
    confidence REAL NOT NULL CHECK (confidence >= 0 AND confidence <= 1),
    explanation TEXT NOT NULL,
    evidence_json TEXT NOT NULL,
    policy_action TEXT NOT NULL,
    status TEXT NOT NULL,
    child_explanation TEXT,
    deduplication_key TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(family_id, id),
    UNIQUE(family_id, device_id, deduplication_key),
    FOREIGN KEY (family_id, child_id, device_id)
        REFERENCES devices(family_id, child_id, id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS incident_evidence (
    id TEXT PRIMARY KEY,
    family_id TEXT NOT NULL,
    incident_id TEXT NOT NULL,
    file_path TEXT NOT NULL,
    content_type TEXT NOT NULL,
    sha256 TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE(family_id, id),
    UNIQUE(family_id, incident_id, sha256),
    FOREIGN KEY (family_id, incident_id)
        REFERENCES incidents(family_id, id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS device_commands (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    family_id TEXT NOT NULL,
    device_id TEXT NOT NULL,
    incident_id TEXT NOT NULL,
    command_type TEXT NOT NULL,
    application TEXT NOT NULL,
    status TEXT NOT NULL,
    created_at TEXT NOT NULL,
    acknowledged_at TEXT,
    UNIQUE(family_id, id),
    FOREIGN KEY (family_id, device_id)
        REFERENCES devices(family_id, id) ON DELETE CASCADE,
    FOREIGN KEY (family_id, incident_id)
        REFERENCES incidents(family_id, id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS app_sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    family_id TEXT NOT NULL,
    child_id TEXT NOT NULL,
    app_name TEXT NOT NULL,
    observed_date TEXT NOT NULL,
    duration_seconds INTEGER NOT NULL CHECK (duration_seconds >= 0),
    FOREIGN KEY (family_id, child_id)
        REFERENCES children(family_id, id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS daily_telemetry (
    family_id TEXT NOT NULL,
    child_id TEXT NOT NULL,
    observed_date TEXT NOT NULL,
    screen_changes INTEGER NOT NULL DEFAULT 0,
    media_sessions INTEGER NOT NULL DEFAULT 0,
    suspicious_events INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (family_id, child_id, observed_date),
    FOREIGN KEY (family_id, child_id)
        REFERENCES children(family_id, id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS auth_sessions (
    id TEXT PRIMARY KEY,
    token_hash TEXT NOT NULL UNIQUE,
    csrf_hash TEXT NOT NULL,
    account_id TEXT NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
    family_id TEXT NOT NULL,
    membership_id TEXT NOT NULL,
    created_at TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    last_seen_at TEXT NOT NULL,
    revoked_at TEXT,
    FOREIGN KEY (account_id, family_id, membership_id)
        REFERENCES memberships(account_id, family_id, id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS login_attempts (
    identifier_hash TEXT NOT NULL,
    attempted_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS password_reset_tokens (
    id TEXT PRIMARY KEY,
    account_id TEXT NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
    token_hash TEXT NOT NULL UNIQUE,
    created_at TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    used_at TEXT
);

CREATE TABLE IF NOT EXISTS pilot_onboarding_events (
    id TEXT PRIMARY KEY,
    family_id TEXT NOT NULL,
    child_id TEXT NOT NULL,
    device_id TEXT,
    session_id TEXT NOT NULL,
    stage TEXT NOT NULL,
    occurred_at TEXT NOT NULL,
    idempotency_key TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE(family_id, id),
    UNIQUE(family_id, idempotency_key),
    FOREIGN KEY (family_id, child_id)
        REFERENCES children(family_id, id) ON DELETE CASCADE,
    FOREIGN KEY (family_id, device_id)
        REFERENCES devices(family_id, id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS agent_health_samples (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    family_id TEXT NOT NULL,
    device_id TEXT NOT NULL,
    agent_version TEXT NOT NULL,
    screen_recording_permission INTEGER NOT NULL,
    accessibility_permission INTEGER NOT NULL,
    observer_healthy INTEGER NOT NULL,
    offline_queue_depth INTEGER NOT NULL,
    protection_status TEXT NOT NULL,
    observed_at TEXT NOT NULL,
    received_at TEXT NOT NULL,
    FOREIGN KEY (family_id, device_id)
        REFERENCES devices(family_id, id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS family_deletion_receipts (
    id TEXT PRIMARY KEY,
    family_reference_sha256 TEXT NOT NULL,
    status TEXT NOT NULL,
    counts_json TEXT NOT NULL,
    staging_directory TEXT,
    requested_at TEXT NOT NULL,
    completed_at TEXT
);

CREATE TABLE IF NOT EXISTS pilot_technical_telemetry (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    family_id TEXT NOT NULL,
    device_id TEXT NOT NULL,
    observed_at TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    FOREIGN KEY (family_id, device_id)
        REFERENCES devices(family_id, id) ON DELETE CASCADE
);
"""

INDEX_SCHEMA = """
CREATE INDEX IF NOT EXISTS idx_incidents_child_occurred
ON incidents(family_id, child_id, occurred_at DESC);

CREATE INDEX IF NOT EXISTS idx_incidents_device_status
ON incidents(family_id, device_id, status);

CREATE INDEX IF NOT EXISTS idx_commands_device_pending
ON device_commands(family_id, device_id, id)
WHERE status = 'PENDING';

CREATE INDEX IF NOT EXISTS idx_sessions_child_date
ON app_sessions(family_id, child_id, observed_date);

CREATE UNIQUE INDEX IF NOT EXISTS idx_evidence_incident_sha256
ON incident_evidence(family_id, incident_id, sha256);

CREATE INDEX IF NOT EXISTS idx_auth_sessions_account_active
ON auth_sessions(account_id, expires_at)
WHERE revoked_at IS NULL;

CREATE INDEX IF NOT EXISTS idx_login_attempts_identifier_time
ON login_attempts(identifier_hash, attempted_at);

CREATE INDEX IF NOT EXISTS idx_pilot_onboarding_stage_time
ON pilot_onboarding_events(family_id, stage, occurred_at);

CREATE INDEX IF NOT EXISTS idx_agent_health_device_received
ON agent_health_samples(family_id, device_id, received_at DESC);
"""

TENANT_TABLES = (
    "device_commands",
    "incident_evidence",
    "daily_telemetry",
    "app_sessions",
    "policies",
    "incidents",
    "devices",
    "children",
)

DEMO_ACCOUNT_ID = "account-demo"
DEMO_FAMILY_ID = "family-demo"
DEMO_MEMBERSHIP_ID = "membership-demo"
DEMO_CHILD_ID = "child-demo"
DEMO_DEVICE_ID = "device-demo"


class GuardianStore:
    def __init__(
        self,
        database_path: Path,
        evidence_directory: Path,
        *,
        environment: Environment = Environment.DEVELOPMENT,
        demo_mode: bool = False,
    ):
        self.database_path = database_path
        self.evidence_directory = evidence_directory
        self.environment = environment
        self.demo_mode = demo_mode

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.database_path, timeout=10)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def initialize(self) -> None:
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self.evidence_directory.mkdir(parents=True, exist_ok=True)
        with self.connect() as connection:
            connection.execute("PRAGMA journal_mode = WAL")
            current_version = connection.execute("PRAGMA user_version").fetchone()[0]
            if current_version > SCHEMA_VERSION:
                raise RuntimeError(
                    f"Database schema version {current_version} is newer than supported version {SCHEMA_VERSION}"
                )
            if current_version == 1:
                self._migrate_v1(connection)
            else:
                connection.executescript(TABLE_SCHEMA)
            if self.demo_mode:
                if self.environment not in {Environment.DEVELOPMENT, Environment.TEST}:
                    raise RuntimeError("Demo mode is forbidden outside development/test")
                self._seed_demo(connection)
            elif self.environment in {Environment.STAGING, Environment.PRODUCTION}:
                self._reject_demo_residue(connection)
            connection.executescript(INDEX_SCHEMA)
            connection.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
            violations = connection.execute("PRAGMA foreign_key_check").fetchall()
            if violations:
                raise RuntimeError("Database migration left foreign-key violations")
            connection.execute("PRAGMA optimize")

    @staticmethod
    def _table_exists(connection: sqlite3.Connection, table: str) -> bool:
        return (
            connection.execute(
                "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
                (table,),
            ).fetchone()
            is not None
        )

    def _migrate_v1(self, connection: sqlite3.Connection) -> None:
        if self.environment not in {Environment.DEVELOPMENT, Environment.TEST} or not self.demo_mode:
            raise RuntimeError("Version 1 data requires explicit local demo mode for migration")
        existing = [table for table in TENANT_TABLES if self._table_exists(connection, table)]
        connection.execute("BEGIN IMMEDIATE")
        for table in existing:
            connection.execute(f"ALTER TABLE {table} RENAME TO {table}_legacy")
        for statement in TABLE_SCHEMA.split(";"):
            if statement.strip():
                connection.execute(statement)
        self._seed_demo_identity(connection)

        if "children" in existing:
            connection.execute(
                """
                INSERT INTO children(id, family_id, name, created_at)
                SELECT id, ?, name, created_at FROM children_legacy
                """,
                (DEMO_FAMILY_ID,),
            )
            self._verify_migrated_count(connection, "children")
        if "devices" in existing:
            connection.execute(
                """
                INSERT INTO devices(
                    id, family_id, child_id, name, platform, paired_at, last_seen_at,
                    lifecycle_status, protection_status
                )
                SELECT id, ?, child_id, name, platform, paired_at, last_seen_at,
                    'ACTIVE', protection_status
                FROM devices_legacy
                """,
                (DEMO_FAMILY_ID,),
            )
            self._verify_migrated_count(connection, "devices")
        if "policies" in existing:
            connection.execute(
                """
                INSERT INTO policies(
                    family_id, child_id, category, action, minimum_risk, minimum_confidence
                )
                SELECT ?, child_id, category, action, minimum_risk, minimum_confidence
                FROM policies_legacy
                """,
                (DEMO_FAMILY_ID,),
            )
            self._verify_migrated_count(connection, "policies")
        if "incidents" in existing:
            connection.execute(
                """
                INSERT INTO incidents(
                    id, family_id, child_id, device_id, application, occurred_at,
                    category, direction, severity, confidence, explanation, evidence_json,
                    policy_action, status, child_explanation, deduplication_key,
                    created_at, updated_at
                )
                SELECT id, ?, child_id, device_id, application, occurred_at,
                    category, direction, severity, confidence, explanation, evidence_json,
                    policy_action, status, child_explanation, deduplication_key,
                    created_at, updated_at
                FROM incidents_legacy
                """,
                (DEMO_FAMILY_ID,),
            )
            self._verify_migrated_count(connection, "incidents")
        if "incident_evidence" in existing:
            connection.execute(
                """
                INSERT INTO incident_evidence(
                    id, family_id, incident_id, file_path, content_type, sha256, created_at
                )
                SELECT id, ?, incident_id, file_path, content_type, sha256, created_at
                FROM incident_evidence_legacy
                """,
                (DEMO_FAMILY_ID,),
            )
            self._verify_migrated_count(connection, "incident_evidence")
        if "device_commands" in existing:
            connection.execute(
                """
                INSERT INTO device_commands(
                    id, family_id, device_id, incident_id, command_type, application,
                    status, created_at, acknowledged_at
                )
                SELECT id, ?, device_id, incident_id, command_type, application,
                    status, created_at, acknowledged_at
                FROM device_commands_legacy
                """,
                (DEMO_FAMILY_ID,),
            )
            self._verify_migrated_count(connection, "device_commands")
        if "app_sessions" in existing:
            connection.execute(
                """
                INSERT INTO app_sessions(
                    id, family_id, child_id, app_name, observed_date, duration_seconds
                )
                SELECT id, ?, child_id, app_name, observed_date, duration_seconds
                FROM app_sessions_legacy
                """,
                (DEMO_FAMILY_ID,),
            )
            self._verify_migrated_count(connection, "app_sessions")
        if "daily_telemetry" in existing:
            connection.execute(
                """
                INSERT INTO daily_telemetry(
                    family_id, child_id, observed_date, screen_changes,
                    media_sessions, suspicious_events
                )
                SELECT ?, child_id, observed_date, screen_changes,
                    media_sessions, suspicious_events
                FROM daily_telemetry_legacy
                """,
                (DEMO_FAMILY_ID,),
            )
            self._verify_migrated_count(connection, "daily_telemetry")
        violations = connection.execute("PRAGMA foreign_key_check").fetchall()
        if violations:
            raise RuntimeError(f"Version 1 migration violated foreign keys: {violations!r}")
        for table in existing:
            connection.execute(f"DROP TABLE {table}_legacy")

    @staticmethod
    def _verify_migrated_count(connection: sqlite3.Connection, table: str) -> None:
        source_count = connection.execute(f"SELECT COUNT(*) FROM {table}_legacy").fetchone()[0]
        target_count = connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        if source_count != target_count:
            raise RuntimeError(
                f"Version 1 migration row-count mismatch for {table}: "
                f"expected {source_count}, got {target_count}"
            )

    @staticmethod
    def _family_reference(family_id: str) -> str:
        return hashlib.sha256(family_id.encode("utf-8")).hexdigest()

    def _seed_demo_identity(self, connection: sqlite3.Connection) -> None:
        now = _now_iso()
        connection.execute(
            """
            INSERT OR IGNORE INTO accounts(
                id, email, password_hash, auth_enabled, status, created_at
            ) VALUES (?, ?, NULL, 0, ?, ?)
            """,
            (
                DEMO_ACCOUNT_ID,
                "guardian.demo@example.invalid",
                AccountStatus.ACTIVE,
                now,
            ),
        )
        connection.execute(
            "INSERT OR IGNORE INTO families(id, name, created_at) VALUES (?, ?, ?)",
            (DEMO_FAMILY_ID, "Família Demo", now),
        )
        connection.execute(
            """
            INSERT OR IGNORE INTO memberships(
                id, account_id, family_id, role, status, created_at
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                DEMO_MEMBERSHIP_ID,
                DEMO_ACCOUNT_ID,
                DEMO_FAMILY_ID,
                MembershipRole.OWNER,
                MembershipStatus.ACTIVE,
                now,
            ),
        )

    def _seed_demo(self, connection: sqlite3.Connection) -> None:
        demo_deleted = connection.execute(
            """
            SELECT 1 FROM family_deletion_receipts
            WHERE family_reference_sha256 = ? AND status IN (?, ?, ?)
            """,
            (
                self._family_reference(DEMO_FAMILY_ID),
                FamilyDeletionStatus.COMPLETED,
                FamilyDeletionStatus.DATABASE_DELETED,
                FamilyDeletionStatus.FAILED_STORAGE_CLEANUP,
            ),
        ).fetchone()
        if demo_deleted is not None:
            return
        self._seed_demo_identity(connection)
        now = _now_iso()
        connection.execute(
            "INSERT OR IGNORE INTO children(id, family_id, name, created_at) VALUES (?, ?, ?, ?)",
            (DEMO_CHILD_ID, DEMO_FAMILY_ID, "Lucas", now),
        )
        connection.execute(
            """
            INSERT OR IGNORE INTO devices(
                id, family_id, child_id, name, platform, paired_at, last_seen_at,
                lifecycle_status
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                DEMO_DEVICE_ID,
                DEMO_FAMILY_ID,
                DEMO_CHILD_ID,
                "MacBook Pro",
                "macOS",
                now,
                None,
                DeviceLifecycleStatus.ACTIVE,
            ),
        )
        defaults = (
            (RiskCategory.ADULT_CONTENT, PolicyAction.BLOCK, 0.82),
            (RiskCategory.HATE_SPEECH, PolicyAction.BLOCK, 0.8),
            (RiskCategory.DANGEROUS_CONTACT, PolicyAction.BLOCK, 0.75),
            (RiskCategory.OTHER, PolicyAction.ALERT, 0.85),
        )
        for category, action, confidence in defaults:
            connection.execute(
                """
                INSERT OR IGNORE INTO policies(
                    family_id, child_id, category, action, minimum_risk, minimum_confidence
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (DEMO_FAMILY_ID, DEMO_CHILD_ID, category, action, RiskLevel.HIGH, confidence),
            )

    @staticmethod
    def _reject_demo_residue(connection: sqlite3.Connection) -> None:
        demo = connection.execute(
            """
            SELECT 1 FROM families WHERE id = ?
            UNION ALL
            SELECT 1 FROM accounts WHERE id = ?
            LIMIT 1
            """,
            (DEMO_FAMILY_ID, DEMO_ACCOUNT_ID),
        ).fetchone()
        if demo is not None:
            raise RuntimeError("staging/production database contains demo data")

    @staticmethod
    def _account_from_row(row: sqlite3.Row) -> Account:
        return Account(
            id=row["id"],
            email=row["email"],
            status=row["status"],
            created_at=row["created_at"],
        )

    @staticmethod
    def _family_from_row(row: sqlite3.Row) -> Family:
        return Family(
            id=row["id"],
            name=row["name"],
            status=row["status"],
            created_at=row["created_at"],
        )

    @staticmethod
    def _membership_from_row(row: sqlite3.Row) -> Membership:
        return Membership(
            id=row["id"],
            account_id=row["account_id"],
            family_id=row["family_id"],
            role=row["role"],
            status=row["status"],
            created_at=row["created_at"],
        )

    def create_account(self, email: str, password_hash: str) -> Account:
        normalized_email = email.strip().casefold()
        if (
            not normalized_email
            or "@" not in normalized_email
            or any(character.isspace() for character in normalized_email)
        ):
            raise ValueError("A valid email address is required")
        if not password_hash:
            raise ValueError("Password hash is required")
        account_id = f"account-{uuid.uuid4().hex[:16]}"
        now = _now_iso()
        with self.connect() as connection:
            connection.execute(
                """
                INSERT INTO accounts(
                    id, email, password_hash, auth_enabled, status, created_at
                ) VALUES (?, ?, ?, 1, ?, ?)
                """,
                (account_id, normalized_email, password_hash, AccountStatus.ACTIVE, now),
            )
            row = connection.execute(
                "SELECT id, email, status, created_at FROM accounts WHERE id = ?",
                (account_id,),
            ).fetchone()
        return self._account_from_row(row)

    def create_family_with_owner(self, account_id: str, name: str) -> tuple[Family, Membership]:
        family_id = f"family-{uuid.uuid4().hex[:16]}"
        membership_id = f"membership-{uuid.uuid4().hex[:16]}"
        family_name = name.strip()
        if not family_name:
            raise ValueError("Family name is required")
        now = _now_iso()
        with self.connect() as connection:
            account = connection.execute(
                "SELECT 1 FROM accounts WHERE id = ? AND status = 'ACTIVE'",
                (account_id,),
            ).fetchone()
            if account is None:
                raise KeyError(account_id)
            connection.execute(
                """
                INSERT INTO families(id, name, status, created_at)
                VALUES (?, ?, ?, ?)
                """,
                (family_id, family_name, FamilyStatus.ACTIVE, now),
            )
            connection.execute(
                """
                INSERT INTO memberships(
                    id, account_id, family_id, role, status, created_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    membership_id,
                    account_id,
                    family_id,
                    MembershipRole.OWNER,
                    MembershipStatus.ACTIVE,
                    now,
                ),
            )
            family_row = connection.execute(
                "SELECT id, name, status, created_at FROM families WHERE id = ?",
                (family_id,),
            ).fetchone()
            membership_row = connection.execute(
                "SELECT * FROM memberships WHERE id = ?",
                (membership_id,),
            ).fetchone()
        return self._family_from_row(family_row), self._membership_from_row(membership_row)

    def add_membership(
        self,
        account_id: str,
        family_id: str,
        role: MembershipRole,
    ) -> Membership:
        membership_id = f"membership-{uuid.uuid4().hex[:16]}"
        now = _now_iso()
        with self.connect() as connection:
            connection.execute(
                """
                INSERT INTO memberships(
                    id, account_id, family_id, role, status, created_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    membership_id,
                    account_id,
                    family_id,
                    role,
                    MembershipStatus.ACTIVE,
                    now,
                ),
            )
            row = connection.execute(
                "SELECT * FROM memberships WHERE id = ?",
                (membership_id,),
            ).fetchone()
        return self._membership_from_row(row)

    def revoke_membership(self, family_id: str, membership_id: str) -> Membership:
        with self.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                """
                SELECT * FROM memberships
                WHERE family_id = ? AND id = ? AND status = 'ACTIVE'
                """,
                (family_id, membership_id),
            ).fetchone()
            if row is None:
                raise KeyError(membership_id)
            if row["role"] == MembershipRole.OWNER:
                other_owner = connection.execute(
                    """
                    SELECT 1 FROM memberships
                    WHERE family_id = ? AND role = 'OWNER' AND status = 'ACTIVE' AND id != ?
                    LIMIT 1
                    """,
                    (family_id, membership_id),
                ).fetchone()
                if other_owner is None:
                    raise ValueError("Cannot revoke the last active owner")
            connection.execute(
                """
                UPDATE memberships SET status = ?, revoked_at = ?
                WHERE family_id = ? AND id = ?
                """,
                (MembershipStatus.REVOKED, _now_iso(), family_id, membership_id),
            )
            revoked = connection.execute(
                "SELECT * FROM memberships WHERE family_id = ? AND id = ?",
                (family_id, membership_id),
            ).fetchone()
        return self._membership_from_row(revoked)

    def get_login_credentials(self, email: str) -> tuple[str, str, bool] | None:
        with self.connect() as connection:
            row = connection.execute(
                """
                SELECT id, password_hash, auth_enabled
                FROM accounts
                WHERE email = ? AND status = 'ACTIVE'
                """,
                (email.strip().casefold(),),
            ).fetchone()
        if row is None or row["password_hash"] is None:
            return None
        return row["id"], row["password_hash"], bool(row["auth_enabled"])

    def active_family_scope(self, account_id: str, family_id: str | None = None) -> FamilyScope | None:
        sql = """
            SELECT membership.id AS membership_id, membership.family_id, membership.role
            FROM memberships membership
            JOIN accounts account ON account.id = membership.account_id
            JOIN families family ON family.id = membership.family_id
            WHERE membership.account_id = ?
              AND membership.status = 'ACTIVE'
              AND account.status = 'ACTIVE'
              AND family.status = 'ACTIVE'
        """
        parameters: list[str] = [account_id]
        if family_id is not None:
            sql += " AND membership.family_id = ?"
            parameters.append(family_id)
        sql += " ORDER BY membership.created_at, membership.id LIMIT 1"
        with self.connect() as connection:
            row = connection.execute(sql, parameters).fetchone()
        if row is None:
            return None
        return FamilyScope(
            account_id=account_id,
            family_id=row["family_id"],
            membership_id=row["membership_id"],
            role=row["role"],
        )

    def create_auth_session(
        self,
        scope: FamilyScope,
        *,
        token_hash: str,
        csrf_hash: str,
        expires_at: datetime,
    ) -> str:
        session_id = f"session-{uuid.uuid4().hex[:16]}"
        now = _now_iso()
        with self.connect() as connection:
            connection.execute(
                """
                INSERT INTO auth_sessions(
                    id, token_hash, csrf_hash, account_id, family_id, membership_id,
                    created_at, expires_at, last_seen_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    session_id,
                    token_hash,
                    csrf_hash,
                    scope.account_id,
                    scope.family_id,
                    scope.membership_id,
                    now,
                    expires_at.isoformat(),
                    now,
                ),
            )
        return session_id

    def resolve_family_scope(self, token_hash: str) -> FamilyScope | None:
        now = _now_iso()
        with self.connect() as connection:
            row = connection.execute(
                """
                SELECT session.account_id, session.family_id, session.membership_id,
                       membership.role
                FROM auth_sessions session
                JOIN accounts account ON account.id = session.account_id
                JOIN families family ON family.id = session.family_id
                JOIN memberships membership
                  ON membership.id = session.membership_id
                 AND membership.account_id = session.account_id
                 AND membership.family_id = session.family_id
                WHERE session.token_hash = ?
                  AND session.revoked_at IS NULL
                  AND session.expires_at > ?
                  AND account.status = 'ACTIVE'
                  AND family.status = 'ACTIVE'
                  AND membership.status = 'ACTIVE'
                """,
                (token_hash, now),
            ).fetchone()
            if row is not None:
                connection.execute(
                    "UPDATE auth_sessions SET last_seen_at = ? WHERE token_hash = ?",
                    (now, token_hash),
                )
        if row is None:
            return None
        return FamilyScope(
            account_id=row["account_id"],
            family_id=row["family_id"],
            membership_id=row["membership_id"],
            role=row["role"],
        )

    def auth_session_csrf_hash(self, token_hash: str) -> str | None:
        with self.connect() as connection:
            row = connection.execute(
                """
                SELECT csrf_hash FROM auth_sessions
                WHERE token_hash = ? AND revoked_at IS NULL AND expires_at > ?
                """,
                (token_hash, _now_iso()),
            ).fetchone()
        return row["csrf_hash"] if row is not None else None

    def revoke_auth_session(self, token_hash: str) -> None:
        with self.connect() as connection:
            connection.execute(
                """
                UPDATE auth_sessions SET revoked_at = ?
                WHERE token_hash = ? AND revoked_at IS NULL
                """,
                (_now_iso(), token_hash),
            )

    def revoke_account_sessions(self, account_id: str) -> None:
        with self.connect() as connection:
            connection.execute(
                """
                UPDATE auth_sessions SET revoked_at = ?
                WHERE account_id = ? AND revoked_at IS NULL
                """,
                (_now_iso(), account_id),
            )

    def login_attempt_count(self, identifier_hash: str, window: timedelta) -> int:
        cutoff = (datetime.now(UTC) - window).isoformat()
        with self.connect() as connection:
            connection.execute("DELETE FROM login_attempts WHERE attempted_at < ?", (cutoff,))
            row = connection.execute(
                "SELECT COUNT(*) AS total FROM login_attempts WHERE identifier_hash = ?",
                (identifier_hash,),
            ).fetchone()
        return row["total"]

    def record_login_attempt(self, identifier_hash: str) -> None:
        with self.connect() as connection:
            connection.execute(
                "INSERT INTO login_attempts(identifier_hash, attempted_at) VALUES (?, ?)",
                (identifier_hash, _now_iso()),
            )

    def clear_login_attempts(self, identifier_hash: str) -> None:
        with self.connect() as connection:
            connection.execute(
                "DELETE FROM login_attempts WHERE identifier_hash = ?",
                (identifier_hash,),
            )

    def account_id_for_recovery(self, email: str) -> str | None:
        with self.connect() as connection:
            row = connection.execute(
                """
                SELECT id FROM accounts
                WHERE email = ? AND status = 'ACTIVE' AND auth_enabled = 1
                """,
                (email.strip().casefold(),),
            ).fetchone()
        return row["id"] if row is not None else None

    def create_password_reset_token(
        self,
        account_id: str,
        token_hash: str,
        expires_at: datetime,
    ) -> None:
        with self.connect() as connection:
            connection.execute(
                "UPDATE password_reset_tokens SET used_at = ? WHERE account_id = ? AND used_at IS NULL",
                (_now_iso(), account_id),
            )
            connection.execute(
                """
                INSERT INTO password_reset_tokens(
                    id, account_id, token_hash, created_at, expires_at
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (
                    f"reset-{uuid.uuid4().hex[:16]}",
                    account_id,
                    token_hash,
                    _now_iso(),
                    expires_at.isoformat(),
                ),
            )

    def consume_password_reset_token(self, token_hash: str, password_hash: str) -> bool:
        now = _now_iso()
        with self.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                """
                SELECT id, account_id FROM password_reset_tokens
                WHERE token_hash = ? AND used_at IS NULL AND expires_at > ?
                """,
                (token_hash, now),
            ).fetchone()
            if row is None:
                return False
            consumed = connection.execute(
                """
                UPDATE password_reset_tokens SET used_at = ?
                WHERE id = ? AND used_at IS NULL AND expires_at > ?
                """,
                (now, row["id"], now),
            )
            if consumed.rowcount != 1:
                return False
            connection.execute(
                "UPDATE accounts SET password_hash = ? WHERE id = ? AND auth_enabled = 1",
                (password_hash, row["account_id"]),
            )
            connection.execute(
                """
                UPDATE auth_sessions SET revoked_at = ?
                WHERE account_id = ? AND revoked_at IS NULL
                """,
                (now, row["account_id"]),
            )
        return True

    def create_child(self, family_id: str, name: str) -> Child:
        child_id = f"child-{uuid.uuid4().hex[:16]}"
        now = _now_iso()
        with self.connect() as connection:
            connection.execute(
                "INSERT INTO children(id, family_id, name, created_at) VALUES (?, ?, ?, ?)",
                (child_id, family_id, name.strip(), now),
            )
        return Child(id=child_id, family_id=family_id, name=name.strip(), created_at=now)

    def list_children(self, family_id: str) -> list[Child]:
        with self.connect() as connection:
            rows = connection.execute(
                """
                SELECT id, family_id, name, created_at
                FROM children WHERE family_id = ? ORDER BY created_at
                """,
                (family_id,),
            ).fetchall()
        return [Child(**dict(row)) for row in rows]

    def child_exists(self, family_id: str, child_id: str) -> bool:
        with self.connect() as connection:
            return (
                connection.execute(
                    "SELECT 1 FROM children WHERE family_id = ? AND id = ?",
                    (family_id, child_id),
                ).fetchone()
                is not None
            )

    def _device_child(self, family_id: str, device_id: str) -> str:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT child_id FROM devices WHERE family_id = ? AND id = ?",
                (family_id, device_id),
            ).fetchone()
        if row is None:
            raise KeyError(device_id)
        return row["child_id"]

    def device_exists(self, family_id: str, device_id: str) -> bool:
        with self.connect() as connection:
            return (
                connection.execute(
                    "SELECT 1 FROM devices WHERE family_id = ? AND id = ?",
                    (family_id, device_id),
                ).fetchone()
                is not None
            )

    def pair_device(self, family_id: str, request: DevicePairRequest) -> Device:
        device_id = f"device-{uuid.uuid4().hex[:12]}"
        now = _now_iso()
        with self.connect() as connection:
            connection.execute(
                """
                INSERT INTO devices(
                    id, family_id, child_id, name, platform, paired_at, last_seen_at,
                    lifecycle_status
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    device_id,
                    family_id,
                    request.child_id,
                    request.device_name,
                    request.platform,
                    now,
                    None,
                    DeviceLifecycleStatus.ACTIVE,
                ),
            )
        return self.get_device(family_id, device_id)

    def get_device(self, family_id: str, device_id: str) -> Device:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT * FROM devices WHERE family_id = ? AND id = ?",
                (family_id, device_id),
            ).fetchone()
        if row is None:
            raise KeyError(device_id)
        protection_status = row["protection_status"]
        if row["lifecycle_status"] != DeviceLifecycleStatus.ACTIVE or row["last_seen_at"] is None:
            protection_status = "DEGRADED"
        else:
            try:
                last_seen_at = datetime.fromisoformat(row["last_seen_at"])
            except ValueError:
                protection_status = "DEGRADED"
            else:
                if last_seen_at < datetime.now(UTC) - HEARTBEAT_STALE_AFTER:
                    protection_status = "DEGRADED"
        return Device(
            id=row["id"],
            family_id=row["family_id"],
            child_id=row["child_id"],
            name=row["name"],
            platform=row["platform"],
            paired_at=row["paired_at"],
            last_seen_at=row["last_seen_at"],
            lifecycle_status=row["lifecycle_status"],
            protection_status=protection_status,
        )

    def list_devices(self, family_id: str) -> list[Device]:
        with self.connect() as connection:
            rows = connection.execute(
                "SELECT id FROM devices WHERE family_id = ? ORDER BY paired_at",
                (family_id,),
            ).fetchall()
        return [self.get_device(family_id, row["id"]) for row in rows]

    def touch_device(self, family_id: str, device_id: str) -> None:
        with self.connect() as connection:
            cursor = connection.execute(
                """
                UPDATE devices SET last_seen_at = ?
                WHERE family_id = ? AND id = ? AND lifecycle_status = 'ACTIVE'
                """,
                (_now_iso(), family_id, device_id),
            )
            if cursor.rowcount == 0:
                raise KeyError(device_id)

    def record_heartbeat(
        self,
        family_id: str,
        device_id: str,
        heartbeat: DeviceHeartbeat,
    ) -> Device:
        received_at = datetime.now(UTC)
        heartbeat_age = (received_at - heartbeat.observed_at).total_seconds()
        healthy = (
            heartbeat.screen_recording_permission
            and heartbeat.accessibility_permission
            and heartbeat.observer_healthy
            and heartbeat_age <= 90
        )
        protection_status = "PROTECTED" if healthy else "DEGRADED"
        with self.connect() as connection:
            cursor = connection.execute(
                """
                UPDATE devices SET last_seen_at = ?, protection_status = ?
                WHERE family_id = ? AND id = ? AND lifecycle_status = 'ACTIVE'
                """,
                (
                    _now_iso(),
                    protection_status,
                    family_id,
                    device_id,
                ),
            )
            if cursor.rowcount == 0:
                raise KeyError(device_id)
            connection.execute(
                """
                INSERT INTO agent_health_samples(
                    family_id, device_id, agent_version, screen_recording_permission,
                    accessibility_permission, observer_healthy, offline_queue_depth,
                    protection_status, observed_at, received_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    family_id,
                    device_id,
                    heartbeat.agent_version,
                    heartbeat.screen_recording_permission,
                    heartbeat.accessibility_permission,
                    heartbeat.observer_healthy,
                    heartbeat.offline_queue_depth,
                    protection_status,
                    heartbeat.observed_at.isoformat(),
                    received_at.isoformat(),
                ),
            )
        return self.get_device(family_id, device_id)

    def record_onboarding_event(
        self, family_id: str, event: PilotOnboardingEventCreate
    ) -> tuple[PilotOnboardingEvent, bool]:
        event_id = f"onb-{uuid.uuid4().hex[:16]}"
        created_at = _now_iso()
        created = True
        with self.connect() as connection:
            child = connection.execute(
                "SELECT 1 FROM children WHERE family_id = ? AND id = ?",
                (family_id, event.child_id),
            ).fetchone()
            if child is None:
                raise KeyError(event.child_id)
            if event.device_id is not None:
                device = connection.execute(
                    "SELECT child_id FROM devices WHERE family_id = ? AND id = ?",
                    (family_id, event.device_id),
                ).fetchone()
                if device is None:
                    raise KeyError(event.device_id)
                if device["child_id"] != event.child_id:
                    raise ValueError("Onboarding device does not belong to child")

            existing = connection.execute(
                """
                SELECT id, child_id, device_id, session_id, stage, occurred_at
                FROM pilot_onboarding_events WHERE family_id = ? AND idempotency_key = ?
                """,
                (family_id, event.idempotency_key),
            ).fetchone()
            if existing is not None:
                if (
                    existing["child_id"] != event.child_id
                    or existing["device_id"] != event.device_id
                    or existing["session_id"] != event.session_id
                    or existing["stage"] != event.stage
                    or datetime.fromisoformat(existing["occurred_at"]) != event.occurred_at
                ):
                    raise ValueError("Onboarding idempotency key was reused with a different event")
                event_id = existing["id"]
                created = False
                return self.get_onboarding_event(family_id, event_id), created

            session_rows = connection.execute(
                """
                SELECT child_id, device_id, stage, occurred_at
                FROM pilot_onboarding_events
                WHERE family_id = ? AND session_id = ?
                ORDER BY created_at, id
                """,
                (family_id, event.session_id),
            ).fetchall()
            canonical_stages = list(PilotOnboardingStage)
            recorded_stages = [PilotOnboardingStage(row["stage"]) for row in session_rows]
            if recorded_stages != canonical_stages[: len(recorded_stages)]:
                raise ValueError("Onboarding session contains a non-canonical stage sequence")
            if len(recorded_stages) >= len(canonical_stages):
                raise ValueError("Onboarding session is already complete")
            expected_stage = canonical_stages[len(recorded_stages)]
            if event.stage != expected_stage:
                raise ValueError(f"Onboarding stage {event.stage} is invalid; expected {expected_stage}")
            if session_rows:
                if any(row["child_id"] != event.child_id for row in session_rows):
                    raise ValueError("Onboarding session cannot change child")
                latest_occurred_at = datetime.fromisoformat(session_rows[-1]["occurred_at"])
                if event.occurred_at <= latest_occurred_at:
                    raise ValueError("Onboarding occurred_at must increase monotonically")
                established_devices = {
                    row["device_id"] for row in session_rows if row["device_id"] is not None
                }
                if established_devices and event.device_id not in established_devices:
                    raise ValueError("Onboarding session cannot change or remove its device")
            device_required_from = canonical_stages.index(PilotOnboardingStage.DEVICE_PAIRED)
            if len(recorded_stages) >= device_required_from and event.device_id is None:
                raise ValueError(f"Onboarding stage {event.stage} requires a device")
            try:
                connection.execute(
                    """
                    INSERT INTO pilot_onboarding_events(
                        id, family_id, child_id, device_id, session_id, stage, occurred_at,
                        idempotency_key, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        event_id,
                        family_id,
                        event.child_id,
                        event.device_id,
                        event.session_id,
                        event.stage,
                        event.occurred_at.isoformat(),
                        event.idempotency_key,
                        created_at,
                    ),
                )
            except sqlite3.IntegrityError as error:
                existing = connection.execute(
                    """
                    SELECT id, child_id, device_id, session_id, stage, occurred_at
                    FROM pilot_onboarding_events WHERE family_id = ? AND idempotency_key = ?
                    """,
                    (family_id, event.idempotency_key),
                ).fetchone()
                if existing is None:
                    raise
                if (
                    existing["child_id"] != event.child_id
                    or existing["device_id"] != event.device_id
                    or existing["session_id"] != event.session_id
                    or existing["stage"] != event.stage
                    or datetime.fromisoformat(existing["occurred_at"]) != event.occurred_at
                ):
                    raise ValueError(
                        "Onboarding idempotency key was reused with a different event"
                    ) from error
                event_id = existing["id"]
                created = False
        return self.get_onboarding_event(family_id, event_id), created

    def get_onboarding_event(self, family_id: str, event_id: str) -> PilotOnboardingEvent:
        with self.connect() as connection:
            row = connection.execute(
                """
                SELECT id, child_id, device_id, session_id, stage, occurred_at, created_at
                FROM pilot_onboarding_events WHERE family_id = ? AND id = ?
                """,
                (family_id, event_id),
            ).fetchone()
        if row is None:
            raise KeyError(event_id)
        return PilotOnboardingEvent(**dict(row))

    @staticmethod
    def _placeholders(values: list[str]) -> str:
        return ",".join("?" for _ in values)

    @staticmethod
    def _remove_empty_staging_directories(staging_directory: Path) -> None:
        directories = sorted(
            (path for path in staging_directory.rglob("*") if path.is_dir()),
            key=lambda path: len(path.parts),
            reverse=True,
        )
        for directory in directories:
            directory.rmdir()
        staging_directory.rmdir()

    def _deletion_counts(
        self,
        connection: sqlite3.Connection,
        family_id: str,
        child_ids: list[str],
        device_ids: list[str],
        incident_ids: list[str],
        evidence_files: int,
    ) -> FamilyDeletionCounts:
        def count_for_ids(table: str, column: str, values: list[str]) -> int:
            if not values:
                return 0
            row = connection.execute(
                f"SELECT COUNT(*) AS total FROM {table} WHERE {column} IN ({self._placeholders(values)})",
                values,
            ).fetchone()
            return int(row["total"])

        return FamilyDeletionCounts(
            families=int(
                connection.execute(
                    "SELECT COUNT(*) AS total FROM families WHERE id = ?", (family_id,)
                ).fetchone()["total"]
            ),
            children=len(child_ids),
            devices=len(device_ids),
            policies=count_for_ids("policies", "child_id", child_ids),
            incidents=len(incident_ids),
            evidence_records=count_for_ids("incident_evidence", "incident_id", incident_ids),
            evidence_files=evidence_files,
            commands=count_for_ids("device_commands", "device_id", device_ids),
            app_sessions=count_for_ids("app_sessions", "child_id", child_ids),
            daily_telemetry=count_for_ids("daily_telemetry", "child_id", child_ids),
            onboarding_events=count_for_ids("pilot_onboarding_events", "child_id", child_ids),
            health_samples=count_for_ids("agent_health_samples", "device_id", device_ids),
        )

    def _set_deletion_status(
        self,
        receipt_id: str,
        status: FamilyDeletionStatus,
        *,
        staging_directory: Path | None = None,
        completed_at: str | None = None,
    ) -> None:
        with self.connect() as connection:
            connection.execute(
                """
                UPDATE family_deletion_receipts
                SET status = ?, staging_directory = ?, completed_at = ?
                WHERE id = ?
                """,
                (
                    status,
                    str(staging_directory) if staging_directory is not None else None,
                    completed_at,
                    receipt_id,
                ),
            )

    def _verify_family_scope_removed(
        self,
        connection: sqlite3.Connection,
        family_id: str,
        child_ids: list[str],
        device_ids: list[str],
        incident_ids: list[str],
    ) -> None:
        remaining: dict[str, int] = {}

        def count_for_ids(table: str, column: str, values: list[str]) -> int:
            if not values:
                return 0
            return int(
                connection.execute(
                    f"SELECT COUNT(*) AS total FROM {table} WHERE {column} IN ({self._placeholders(values)})",
                    values,
                ).fetchone()["total"]
            )

        remaining["families"] = int(
            connection.execute(
                "SELECT COUNT(*) AS total FROM families WHERE id = ?", (family_id,)
            ).fetchone()["total"]
        )
        for table in ("children", "policies", "app_sessions", "daily_telemetry", "pilot_onboarding_events"):
            remaining[table] = count_for_ids(table, "child_id" if table != "children" else "id", child_ids)
        remaining["devices"] = count_for_ids("devices", "id", device_ids)
        remaining["agent_health_samples"] = count_for_ids("agent_health_samples", "device_id", device_ids)
        remaining["device_commands"] = count_for_ids("device_commands", "device_id", device_ids)
        remaining["incidents"] = count_for_ids("incidents", "id", incident_ids)
        remaining["incident_evidence"] = count_for_ids("incident_evidence", "incident_id", incident_ids)
        orphaned = {table: total for table, total in remaining.items() if total}
        if orphaned:
            summary = ", ".join(f"{table}={total}" for table, total in sorted(orphaned.items()))
            raise RuntimeError(f"Family deletion verification found remaining records: {summary}")

    def get_family_deletion_receipt(self, receipt_id: str) -> FamilyDeletionReceipt:
        with self.connect() as connection:
            row = connection.execute(
                """
                SELECT id, family_reference_sha256, status, counts_json,
                       requested_at, completed_at
                FROM family_deletion_receipts WHERE id = ?
                """,
                (receipt_id,),
            ).fetchone()
        if row is None:
            raise KeyError(receipt_id)
        return FamilyDeletionReceipt(
            id=row["id"],
            family_reference_sha256=row["family_reference_sha256"],
            status=row["status"],
            counts=FamilyDeletionCounts.model_validate_json(row["counts_json"]),
            requested_at=row["requested_at"],
            completed_at=row["completed_at"],
        )

    def delete_family(self, family_id: str) -> FamilyDeletionReceipt:
        """Delete the complete family scope implemented by the local control plane."""
        receipt_id = f"del-{uuid.uuid4().hex[:16]}"
        requested_at = _now_iso()
        evidence_root = self.evidence_directory.resolve()
        with self.connect() as connection:
            family = connection.execute("SELECT 1 FROM families WHERE id = ?", (family_id,)).fetchone()
            if family is None:
                raise KeyError(family_id)
            child_ids = [
                row["id"]
                for row in connection.execute(
                    "SELECT id FROM children WHERE family_id = ?", (family_id,)
                ).fetchall()
            ]
            device_ids = (
                [
                    row["id"]
                    for row in connection.execute(
                        f"SELECT id FROM devices WHERE child_id IN ({self._placeholders(child_ids)})",
                        child_ids,
                    ).fetchall()
                ]
                if child_ids
                else []
            )
            incident_ids = (
                [
                    row["id"]
                    for row in connection.execute(
                        f"SELECT id FROM incidents WHERE child_id IN ({self._placeholders(child_ids)})",
                        child_ids,
                    ).fetchall()
                ]
                if child_ids
                else []
            )
            evidence_rows = (
                connection.execute(
                    f"""
                    SELECT file_path FROM incident_evidence
                    WHERE incident_id IN ({self._placeholders(incident_ids)})
                    """,
                    incident_ids,
                ).fetchall()
                if incident_ids
                else []
            )
            source_files: list[Path] = []
            for row in evidence_rows:
                source = Path(row["file_path"]).resolve()
                if evidence_root not in source.parents:
                    raise ValueError("Family evidence path escapes the configured evidence directory")
                if source.is_file():
                    source_files.append(source)
            counts = self._deletion_counts(
                connection,
                family_id,
                child_ids,
                device_ids,
                incident_ids,
                len(source_files),
            )
            connection.execute(
                """
                INSERT INTO family_deletion_receipts(
                    id, family_reference_sha256, status, counts_json,
                    staging_directory, requested_at, completed_at
                ) VALUES (?, ?, ?, ?, NULL, ?, NULL)
                """,
                (
                    receipt_id,
                    self._family_reference(family_id),
                    FamilyDeletionStatus.STARTED,
                    counts.model_dump_json(),
                    requested_at,
                ),
            )

        staging_directory = evidence_root / ".deletion-staging" / receipt_id
        staged_files: list[tuple[Path, Path]] = []
        try:
            if source_files:
                staging_directory.mkdir(parents=True, exist_ok=False)
                for source in source_files:
                    staged = staging_directory / source.relative_to(evidence_root)
                    staged.parent.mkdir(parents=True, exist_ok=True)
                    source.replace(staged)
                    staged_files.append((source, staged))
                self._set_deletion_status(
                    receipt_id,
                    FamilyDeletionStatus.STARTED,
                    staging_directory=staging_directory,
                )
        except OSError as error:
            restore_errors: list[OSError] = []
            for source, staged in staged_files:
                if staged.is_file():
                    if source.exists():
                        restore_errors.append(FileExistsError(source.name))
                        continue
                    source.parent.mkdir(parents=True, exist_ok=True)
                    try:
                        staged.replace(source)
                    except OSError as restore_error:
                        restore_errors.append(restore_error)
            if staging_directory.is_dir():
                try:
                    self._remove_empty_staging_directories(staging_directory)
                except OSError:
                    pass
            self._set_deletion_status(
                receipt_id,
                FamilyDeletionStatus.FAILED_DATABASE,
                staging_directory=staging_directory if staging_directory.exists() else None,
            )
            if restore_errors:
                error_types = ", ".join(type(item).__name__ for item in restore_errors)
                raise RuntimeError(
                    "Unable to stage family evidence and staging rollback was incomplete "
                    f"({len(restore_errors)} restore error(s): {error_types})"
                ) from error
            raise RuntimeError("Unable to stage family evidence for deletion") from error

        try:
            with self.connect() as connection:
                if device_ids:
                    placeholders = self._placeholders(device_ids)
                    connection.execute(
                        f"DELETE FROM device_commands WHERE device_id IN ({placeholders})", device_ids
                    )
                    connection.execute(
                        f"DELETE FROM agent_health_samples WHERE device_id IN ({placeholders})",
                        device_ids,
                    )
                if incident_ids:
                    placeholders = self._placeholders(incident_ids)
                    connection.execute(
                        f"DELETE FROM incident_evidence WHERE incident_id IN ({placeholders})",
                        incident_ids,
                    )
                    connection.execute(f"DELETE FROM incidents WHERE id IN ({placeholders})", incident_ids)
                if child_ids:
                    placeholders = self._placeholders(child_ids)
                    for table in (
                        "pilot_onboarding_events",
                        "daily_telemetry",
                        "app_sessions",
                        "policies",
                    ):
                        connection.execute(
                            f"DELETE FROM {table} WHERE child_id IN ({placeholders})", child_ids
                        )
                    connection.execute(f"DELETE FROM devices WHERE child_id IN ({placeholders})", child_ids)
                    connection.execute(f"DELETE FROM children WHERE id IN ({placeholders})", child_ids)
                connection.execute("DELETE FROM families WHERE id = ?", (family_id,))
                self._verify_family_scope_removed(
                    connection,
                    family_id,
                    child_ids,
                    device_ids,
                    incident_ids,
                )
                connection.execute(
                    "UPDATE family_deletion_receipts SET status = ? WHERE id = ?",
                    (FamilyDeletionStatus.DATABASE_DELETED, receipt_id),
                )
        except Exception as database_error:
            restore_errors: list[OSError] = []
            for source, staged in staged_files:
                if staged.is_file():
                    if source.exists():
                        restore_errors.append(FileExistsError(source.name))
                        continue
                    source.parent.mkdir(parents=True, exist_ok=True)
                    try:
                        staged.replace(source)
                    except OSError as restore_error:
                        restore_errors.append(restore_error)
            if staging_directory.is_dir():
                try:
                    self._remove_empty_staging_directories(staging_directory)
                except OSError:
                    pass
            self._set_deletion_status(
                receipt_id,
                FamilyDeletionStatus.FAILED_DATABASE,
                staging_directory=staging_directory if staging_directory.exists() else None,
            )
            if restore_errors:
                error_types = ", ".join(type(error).__name__ for error in restore_errors)
                raise RuntimeError(
                    "Family database deletion failed and evidence rollback was incomplete "
                    f"({len(restore_errors)} restore error(s): {error_types})"
                ) from database_error
            raise

        try:
            for _, staged in staged_files:
                staged.unlink(missing_ok=True)
            if staging_directory.is_dir():
                self._remove_empty_staging_directories(staging_directory)
            staging_root = evidence_root / ".deletion-staging"
            if staging_root.is_dir():
                try:
                    staging_root.rmdir()
                except OSError:
                    pass
        except OSError as error:
            self._set_deletion_status(
                receipt_id,
                FamilyDeletionStatus.FAILED_STORAGE_CLEANUP,
                staging_directory=staging_directory,
            )
            raise RuntimeError("Family database deleted but evidence cleanup is incomplete") from error

        self._set_deletion_status(
            receipt_id,
            FamilyDeletionStatus.COMPLETED,
            completed_at=_now_iso(),
        )
        return self.get_family_deletion_receipt(receipt_id)

    def resume_family_deletion(self, receipt_id: str) -> FamilyDeletionReceipt:
        """Resume staged cleanup, or restore evidence after a rolled-back DB deletion."""
        with self.connect() as connection:
            row = connection.execute(
                """
                SELECT status, staging_directory
                FROM family_deletion_receipts WHERE id = ?
                """,
                (receipt_id,),
            ).fetchone()
        if row is None:
            raise KeyError(receipt_id)
        status = FamilyDeletionStatus(row["status"])
        if status == FamilyDeletionStatus.COMPLETED:
            return self.get_family_deletion_receipt(receipt_id)
        if status not in {
            FamilyDeletionStatus.DATABASE_DELETED,
            FamilyDeletionStatus.FAILED_DATABASE,
            FamilyDeletionStatus.FAILED_STORAGE_CLEANUP,
        }:
            raise ValueError(f"Deletion receipt {receipt_id} cannot resume from {status}")

        evidence_root = self.evidence_directory.resolve()
        staging_root = (evidence_root / ".deletion-staging").resolve()
        configured_staging = row["staging_directory"]
        if configured_staging is None:
            if status == FamilyDeletionStatus.FAILED_DATABASE:
                return self.get_family_deletion_receipt(receipt_id)
            self._set_deletion_status(
                receipt_id,
                FamilyDeletionStatus.COMPLETED,
                completed_at=_now_iso(),
            )
            return self.get_family_deletion_receipt(receipt_id)

        staging_directory = Path(configured_staging).resolve()
        if staging_directory.parent != staging_root or staging_directory.name != receipt_id:
            raise ValueError("Deletion receipt staging directory is outside the configured staging root")

        entries = list(staging_directory.rglob("*")) if staging_directory.is_dir() else []
        staged_files: list[Path] = []
        for entry in entries:
            resolved_entry = entry.resolve()
            if (
                entry.is_symlink()
                or staging_directory not in resolved_entry.parents
                or (not entry.is_file() and not entry.is_dir())
            ):
                raise ValueError("Deletion staging contains an unsupported entry")
            if entry.is_file():
                staged_files.append(entry)

        if status == FamilyDeletionStatus.FAILED_DATABASE:
            destinations = [evidence_root / staged.relative_to(staging_directory) for staged in staged_files]
            for destination in destinations:
                if destination.exists():
                    raise FileExistsError(f"Refusing to overwrite restored evidence {destination.name}")
            for staged, destination in zip(staged_files, destinations, strict=True):
                destination.parent.mkdir(parents=True, exist_ok=True)
                staged.replace(destination)
            terminal_status = FamilyDeletionStatus.FAILED_DATABASE
            completed_at = None
        else:
            for staged in staged_files:
                staged.unlink()
            terminal_status = FamilyDeletionStatus.COMPLETED
            completed_at = _now_iso()

        if staging_directory.is_dir():
            self._remove_empty_staging_directories(staging_directory)
        if staging_root.is_dir():
            try:
                staging_root.rmdir()
            except OSError:
                pass
        self._set_deletion_status(
            receipt_id,
            terminal_status,
            completed_at=completed_at,
        )
        return self.get_family_deletion_receipt(receipt_id)

    @staticmethod
    def _percentile(values: list[float], percentile: float) -> float | None:
        if not values:
            return None
        ordered = sorted(values)
        index = max(0, min(len(ordered) - 1, int((len(ordered) * percentile) + 0.999999) - 1))
        return round(ordered[index], 3)

    def pilot_metrics(self, since_hours: int, *, family_id: str | None = None) -> PilotMetricsReport:
        generated_at = datetime.now(UTC)
        window_started_at = generated_at - timedelta(hours=since_hours)
        window_start = window_started_at.isoformat()
        with self.connect() as connection:
            funnel_rows = connection.execute(
                """
                SELECT stage, COUNT(*) AS event_count,
                       COUNT(DISTINCT session_id) AS unique_sessions
                FROM pilot_onboarding_events
                WHERE occurred_at >= ? AND (? IS NULL OR family_id = ?)
                GROUP BY stage
                """,
                (window_start, family_id, family_id),
            ).fetchall()
            health_rows = connection.execute(
                """
                SELECT device_id, protection_status, offline_queue_depth, observed_at
                FROM agent_health_samples
                WHERE received_at >= ? AND (? IS NULL OR family_id = ?)
                ORDER BY received_at
                """,
                (window_start, family_id, family_id),
            ).fetchall()
            command_rows = connection.execute(
                """
                SELECT created_at, acknowledged_at
                FROM device_commands
                WHERE acknowledged_at IS NOT NULL AND created_at >= ?
                  AND (? IS NULL OR family_id = ?)
                """,
                (window_start, family_id, family_id),
            ).fetchall()
            deletion_failures = connection.execute(
                """
                SELECT COUNT(*) AS total FROM family_deletion_receipts
                WHERE requested_at >= ? AND status IN (?, ?)
                  AND (? IS NULL OR family_reference_sha256 = ?)
                """,
                (
                    window_start,
                    FamilyDeletionStatus.FAILED_DATABASE,
                    FamilyDeletionStatus.FAILED_STORAGE_CLEANUP,
                    family_id,
                    self._family_reference(family_id) if family_id is not None else None,
                ),
            ).fetchone()["total"]

        funnel_by_stage = {row["stage"]: dict(row) for row in funnel_rows}
        onboarding = [
            PilotFunnelStageMetric(
                stage=stage,
                event_count=funnel_by_stage.get(stage, {}).get("event_count", 0),
                unique_sessions=funnel_by_stage.get(stage, {}).get("unique_sessions", 0),
            )
            for stage in PilotOnboardingStage
        ]
        healthy_count = sum(row["protection_status"] == "PROTECTED" for row in health_rows)
        health_percent = round((healthy_count / len(health_rows)) * 100, 3) if health_rows else None
        latest_by_device: dict[str, datetime] = {}
        for row in health_rows:
            observed_at = datetime.fromisoformat(row["observed_at"])
            if observed_at.tzinfo is None:
                observed_at = observed_at.replace(tzinfo=UTC)
            current = latest_by_device.get(row["device_id"])
            if current is None or observed_at > current:
                latest_by_device[row["device_id"]] = observed_at
        heartbeat_ages = [
            max(0.0, (generated_at - value).total_seconds()) for value in latest_by_device.values()
        ]
        latencies_ms = [
            max(
                0.0,
                (
                    datetime.fromisoformat(row["acknowledged_at"]) - datetime.fromisoformat(row["created_at"])
                ).total_seconds()
                * 1000,
            )
            for row in command_rows
        ]
        return PilotMetricsReport(
            window_started_at=window_started_at,
            generated_at=generated_at,
            onboarding=onboarding,
            health_sample_count=len(health_rows),
            healthy_health_sample_count=healthy_count,
            agent_health_percent=health_percent,
            heartbeat_age_max_seconds=round(max(heartbeat_ages), 3) if heartbeat_ages else None,
            offline_queue_depth_max=(
                max(row["offline_queue_depth"] for row in health_rows) if health_rows else None
            ),
            command_ack_count=len(latencies_ms),
            command_ack_latency_p50_ms=self._percentile(latencies_ms, 0.50),
            command_ack_latency_p95_ms=self._percentile(latencies_ms, 0.95),
            command_ack_latency_max_ms=round(max(latencies_ms), 3) if latencies_ms else None,
            family_deletion_failures=deletion_failures,
        )

    def get_policy(self, family_id: str, child_id: str) -> list[PolicyRule]:
        with self.connect() as connection:
            rows = connection.execute(
                """
                SELECT category, action, minimum_risk, minimum_confidence
                FROM policies WHERE family_id = ? AND child_id = ? ORDER BY category
                """,
                (family_id, child_id),
            ).fetchall()
        return [PolicyRule(**dict(row)) for row in rows]

    def replace_policy(self, family_id: str, child_id: str, rules: list[PolicyRule]) -> list[PolicyRule]:
        with self.connect() as connection:
            connection.execute(
                "DELETE FROM policies WHERE family_id = ? AND child_id = ?",
                (family_id, child_id),
            )
            connection.executemany(
                """
                INSERT INTO policies(
                    family_id, child_id, category, action, minimum_risk, minimum_confidence
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        family_id,
                        child_id,
                        rule.category,
                        rule.action,
                        rule.minimum_risk,
                        rule.minimum_confidence,
                    )
                    for rule in rules
                ],
            )
        return self.get_policy(family_id, child_id)

    def create_incident(self, family_id: str, request: IncidentCreate) -> tuple[Incident, bool]:
        if request.assessment.category is None or request.assessment.direction is None:
            raise ValueError("SAFE assessments cannot create incidents")

        device_child_id = self._device_child(family_id, request.device_id)
        if device_child_id != request.child_id or not self.child_exists(family_id, request.child_id):
            raise KeyError(request.child_id)

        incident_id = f"inc-{uuid.uuid4().hex[:16]}"
        status = (
            IncidentStatus.BLOCKED
            if request.decision.action == EnforcementAction.BLOCK
            else IncidentStatus.DETECTED
        )
        now = _now_iso()
        created = True

        def values(key: str) -> tuple[object, ...]:
            return (
                incident_id,
                family_id,
                request.child_id,
                request.device_id,
                request.application,
                request.occurred_at.isoformat(),
                request.assessment.category,
                request.assessment.direction,
                request.assessment.risk,
                request.assessment.confidence,
                request.assessment.explanation,
                json.dumps(request.assessment.evidence, ensure_ascii=False),
                request.decision.action,
                status,
                key,
                now,
                now,
            )

        insert_sql = """
            INSERT INTO incidents(
                id, family_id, child_id, device_id, application, occurred_at, category, direction,
                severity, confidence, explanation, evidence_json, policy_action, status,
                deduplication_key, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        with self.connect() as connection:
            try:
                connection.execute(insert_sql, values(request.deduplication_key))
            except sqlite3.IntegrityError as error:
                duplicate = connection.execute(
                    """
                    SELECT id, status FROM incidents
                    WHERE family_id = ? AND device_id = ? AND deduplication_key = ?
                    """,
                    (family_id, request.device_id, request.deduplication_key),
                ).fetchone()
                if duplicate is None:
                    raise error
                if duplicate["status"] == IncidentStatus.UNLOCKED:
                    incident_id = f"inc-{uuid.uuid4().hex[:16]}"
                    replay_key = f"{request.deduplication_key}:{uuid.uuid4().hex[:8]}"
                    connection.execute(insert_sql, values(replay_key))
                else:
                    incident_id = duplicate["id"]
                    created = False
        return self.get_incident(family_id, incident_id), created

    def _incident_from_row(self, row: sqlite3.Row, screenshot_urls: list[str]) -> Incident:
        return Incident(
            id=row["id"],
            family_id=row["family_id"],
            child_id=row["child_id"],
            device_id=row["device_id"],
            application=row["application"],
            occurred_at=row["occurred_at"],
            category=row["category"],
            direction=row["direction"],
            severity=row["severity"],
            confidence=row["confidence"],
            explanation=row["explanation"],
            evidence=json.loads(row["evidence_json"]),
            policy_action=row["policy_action"],
            status=row["status"],
            child_explanation=row["child_explanation"],
            screenshot_urls=screenshot_urls,
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    def get_incident(self, family_id: str, incident_id: str) -> Incident:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT * FROM incidents WHERE family_id = ? AND id = ?",
                (family_id, incident_id),
            ).fetchone()
            evidence_rows = connection.execute(
                """
                SELECT id FROM incident_evidence
                WHERE family_id = ? AND incident_id = ? ORDER BY created_at
                """,
                (family_id, incident_id),
            ).fetchall()
        if row is None:
            raise KeyError(incident_id)
        urls = [f"/api/evidence/{item['id']}" for item in evidence_rows]
        return self._incident_from_row(row, urls)

    def list_incidents(
        self, family_id: str, child_id: str, limit: int, status: IncidentStatus | None = None
    ) -> list[Incident]:
        if not self.child_exists(family_id, child_id):
            raise KeyError(child_id)
        sql = "SELECT id FROM incidents WHERE family_id = ? AND child_id = ?"
        parameters: list[object] = [family_id, child_id]
        if status is not None:
            sql += " AND status = ?"
            parameters.append(status)
        sql += " ORDER BY occurred_at DESC LIMIT ?"
        parameters.append(limit)
        with self.connect() as connection:
            rows = connection.execute(sql, parameters).fetchall()
        return [self.get_incident(family_id, row["id"]) for row in rows]

    def request_unlock(self, family_id: str, incident_id: str, explanation: str) -> Incident:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT status FROM incidents WHERE family_id = ? AND id = ?",
                (family_id, incident_id),
            ).fetchone()
            if row is None:
                raise KeyError(incident_id)
            if row["status"] not in (IncidentStatus.BLOCKED, IncidentStatus.UNLOCK_REQUESTED):
                raise ValueError(f"Cannot request unlock from status {row['status']}")
            connection.execute(
                """
                UPDATE incidents
                SET status = ?, child_explanation = ?, updated_at = ?
                WHERE family_id = ? AND id = ?
                """,
                (IncidentStatus.UNLOCK_REQUESTED, explanation, _now_iso(), family_id, incident_id),
            )
        return self.get_incident(family_id, incident_id)

    def unlock_incident(
        self,
        family_id: str,
        incident_id: str,
        *,
        command_created_at: datetime | None = None,
    ) -> Incident:
        with self.connect() as connection:
            row = connection.execute(
                """
                SELECT family_id, status, device_id, application FROM incidents
                WHERE family_id = ? AND id = ?
                """,
                (family_id, incident_id),
            ).fetchone()
            if row is None:
                raise KeyError(incident_id)
            if row["status"] == IncidentStatus.UNLOCKED:
                return self.get_incident(family_id, incident_id)
            if row["status"] not in (IncidentStatus.BLOCKED, IncidentStatus.UNLOCK_REQUESTED):
                raise ValueError(f"Cannot unlock incident from status {row['status']}")
            if command_created_at is not None and command_created_at.tzinfo is None:
                raise ValueError("Command timestamp must be timezone-aware")
            now = (command_created_at or datetime.now(UTC)).isoformat()
            connection.execute(
                """
                UPDATE incidents SET status = ?, updated_at = ?
                WHERE family_id = ? AND id = ?
                """,
                (IncidentStatus.UNLOCKED, now, family_id, incident_id),
            )
            connection.execute(
                """
                INSERT INTO device_commands(
                    family_id, device_id, incident_id, command_type, application, status, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    row["family_id"],
                    row["device_id"],
                    incident_id,
                    CommandType.UNLOCK_APPLICATION,
                    row["application"],
                    CommandStatus.PENDING,
                    now,
                ),
            )
        return self.get_incident(family_id, incident_id)

    def keep_blocked(self, family_id: str, incident_id: str) -> Incident:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT status FROM incidents WHERE family_id = ? AND id = ?",
                (family_id, incident_id),
            ).fetchone()
            if row is None:
                raise KeyError(incident_id)
            if row["status"] not in (IncidentStatus.BLOCKED, IncidentStatus.UNLOCK_REQUESTED):
                raise ValueError(f"Cannot keep blocked from status {row['status']}")
            connection.execute(
                """
                UPDATE incidents SET status = ?, updated_at = ?
                WHERE family_id = ? AND id = ?
                """,
                (IncidentStatus.KEPT_BLOCKED, _now_iso(), family_id, incident_id),
            )
        return self.get_incident(family_id, incident_id)

    def save_evidence(self, family_id: str, incident_id: str, data: bytes, content_type: str) -> str:
        incident = self.get_incident(family_id, incident_id)
        suffixes = {"image/png": ".png", "image/jpeg": ".jpg", "image/webp": ".webp", "text/plain": ".txt"}
        suffix = suffixes[content_type]
        digest = hashlib.sha256(data).hexdigest()
        with self.connect() as connection:
            existing = connection.execute(
                """
                SELECT id FROM incident_evidence
                WHERE family_id = ? AND incident_id = ? AND sha256 = ?
                """,
                (family_id, incident_id, digest),
            ).fetchone()
        if existing is not None:
            return existing["id"]
        evidence_id = f"ev-{uuid.uuid4().hex[:16]}"
        destination = self.evidence_directory / f"{evidence_id}{suffix}"
        destination.write_bytes(data)
        try:
            with self.connect() as connection:
                connection.execute(
                    """
                    INSERT INTO incident_evidence(
                        id, family_id, incident_id, file_path, content_type, sha256, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        evidence_id,
                        incident.family_id,
                        incident_id,
                        str(destination.resolve()),
                        content_type,
                        digest,
                        _now_iso(),
                    ),
                )
        except Exception:
            destination.unlink(missing_ok=True)
            raise
        return evidence_id

    def get_evidence(self, family_id: str, evidence_id: str) -> tuple[Path, str]:
        with self.connect() as connection:
            row = connection.execute(
                """
                SELECT file_path, content_type FROM incident_evidence
                WHERE family_id = ? AND id = ?
                """,
                (family_id, evidence_id),
            ).fetchone()
        if row is None:
            raise KeyError(evidence_id)
        path = Path(row["file_path"]).resolve()
        evidence_root = self.evidence_directory.resolve()
        if evidence_root not in path.parents or not path.is_file():
            raise FileNotFoundError(evidence_id)
        return path, row["content_type"]

    def pending_commands(self, family_id: str, device_id: str, after_id: int) -> list[DeviceCommand]:
        if not self.device_exists(family_id, device_id):
            raise KeyError(device_id)
        with self.connect() as connection:
            rows = connection.execute(
                """
                SELECT id, device_id, incident_id, command_type AS type, application, status,
                       created_at, acknowledged_at
                FROM device_commands
                WHERE family_id = ? AND device_id = ? AND status = ? AND id > ?
                ORDER BY id
                """,
                (family_id, device_id, CommandStatus.PENDING, after_id),
            ).fetchall()
        return [DeviceCommand(**dict(row)) for row in rows]

    def acknowledge_command(self, family_id: str, device_id: str, command_id: int) -> DeviceCommand:
        with self.connect() as connection:
            cursor = connection.execute(
                """
                UPDATE device_commands
                SET status = ?, acknowledged_at = ?
                WHERE family_id = ? AND id = ? AND device_id = ? AND status = ?
                """,
                (
                    CommandStatus.ACKNOWLEDGED,
                    _now_iso(),
                    family_id,
                    command_id,
                    device_id,
                    CommandStatus.PENDING,
                ),
            )
            if cursor.rowcount == 0:
                existing = connection.execute(
                    """
                    SELECT 1 FROM device_commands
                    WHERE family_id = ? AND id = ? AND device_id = ?
                    """,
                    (family_id, command_id, device_id),
                ).fetchone()
                if existing is None:
                    raise KeyError(command_id)
            row = connection.execute(
                """
                SELECT id, device_id, incident_id, command_type AS type, application, status,
                       created_at, acknowledged_at
                FROM device_commands WHERE family_id = ? AND id = ?
                """,
                (family_id, command_id),
            ).fetchone()
        return DeviceCommand(**dict(row))

    def record_telemetry(self, family_id: str, device_id: str, update: TelemetryUpdate) -> None:
        child_id = self._device_child(family_id, device_id)
        if update.child_id != child_id:
            raise ValueError("Telemetry child must match the paired device")
        observed_date = update.observed_at.date().isoformat()
        with self.connect() as connection:
            if update.app_name and update.session_seconds:
                connection.execute(
                    """
                    INSERT INTO app_sessions(
                        family_id, child_id, app_name, observed_date, duration_seconds
                    ) VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        family_id,
                        update.child_id,
                        update.app_name,
                        observed_date,
                        update.session_seconds,
                    ),
                )
            connection.execute(
                """
                INSERT INTO daily_telemetry(
                    family_id, child_id, observed_date, screen_changes,
                    media_sessions, suspicious_events
                ) VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(family_id, child_id, observed_date) DO UPDATE SET
                    screen_changes = screen_changes + excluded.screen_changes,
                    media_sessions = media_sessions + excluded.media_sessions,
                    suspicious_events = suspicious_events + excluded.suspicious_events
                """,
                (
                    family_id,
                    update.child_id,
                    observed_date,
                    update.screen_changes,
                    update.media_sessions,
                    update.suspicious_events,
                ),
            )

    def record_pilot_telemetry(
        self, family_id: str, device_id: str, update: PilotTechnicalTelemetry
    ) -> None:
        self.touch_device(family_id, device_id)
        with self.connect() as connection:
            connection.execute(
                """
                INSERT INTO pilot_technical_telemetry(
                    family_id, device_id, observed_at, payload_json
                ) VALUES (?, ?, ?, ?)
                """,
                (family_id, device_id, _now_iso(), update.model_dump_json(exclude_none=True)),
            )

    def daily_report(self, family_id: str, child_id: str, report_date: date) -> DailyReport:
        date_value = report_date.isoformat()
        with self.connect() as connection:
            child = connection.execute(
                "SELECT name FROM children WHERE family_id = ? AND id = ?",
                (family_id, child_id),
            ).fetchone()
            if child is None:
                raise KeyError(child_id)
            apps = connection.execute(
                """
                SELECT app_name AS app, SUM(duration_seconds) AS seconds
                FROM app_sessions
                WHERE family_id = ? AND child_id = ? AND observed_date = ?
                GROUP BY app_name
                ORDER BY seconds DESC
                """,
                (family_id, child_id, date_value),
            ).fetchall()
            incident_counts = connection.execute(
                """
                SELECT COUNT(*) AS incident_count,
                       SUM(CASE WHEN policy_action = 'BLOCK' THEN 1 ELSE 0 END) AS interventions
                FROM incidents
                WHERE family_id = ? AND child_id = ? AND substr(occurred_at, 1, 10) = ?
                """,
                (family_id, child_id, date_value),
            ).fetchone()
            telemetry = connection.execute(
                """
                SELECT screen_changes, media_sessions, suspicious_events
                FROM daily_telemetry
                WHERE family_id = ? AND child_id = ? AND observed_date = ?
                """,
                (family_id, child_id, date_value),
            ).fetchone()
            evidence_count = connection.execute(
                """
                SELECT COUNT(*) AS total
                FROM incident_evidence evidence
                JOIN incidents incident ON incident.id = evidence.incident_id
                WHERE incident.family_id = ? AND incident.child_id = ?
                    AND substr(incident.occurred_at, 1, 10) = ?
                """,
                (family_id, child_id, date_value),
            ).fetchone()["total"]
        usage = [DailyAppUsage(**dict(row)) for row in apps]
        return DailyReport(
            family_id=family_id,
            child_id=child_id,
            child_name=child["name"],
            date=date_value,
            total_seconds=sum(item.seconds for item in usage),
            apps=usage,
            incident_count=incident_counts["incident_count"] or 0,
            interventions=incident_counts["interventions"] or 0,
            screen_changes=telemetry["screen_changes"] if telemetry else 0,
            media_sessions=telemetry["media_sessions"] if telemetry else 0,
            suspicious_events=telemetry["suspicious_events"] if telemetry else 0,
            evidence_count=evidence_count or 0,
        )
