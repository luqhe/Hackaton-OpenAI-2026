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
    Incident,
    IncidentCreate,
    IncidentStatus,
    PolicyAction,
    PolicyRule,
    RiskCategory,
    RiskLevel,
    TelemetryUpdate,
)
from guardian_core.version import SCHEMA_VERSION


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
            row = connection.execute(
                """
                SELECT id, account_id FROM password_reset_tokens
                WHERE token_hash = ? AND used_at IS NULL AND expires_at > ?
                """,
                (token_hash, now),
            ).fetchone()
            if row is None:
                return False
            connection.execute(
                "UPDATE password_reset_tokens SET used_at = ? WHERE id = ?",
                (now, row["id"]),
            )
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
        return Device(
            id=row["id"],
            family_id=row["family_id"],
            child_id=row["child_id"],
            name=row["name"],
            platform=row["platform"],
            paired_at=row["paired_at"],
            last_seen_at=row["last_seen_at"],
            lifecycle_status=row["lifecycle_status"],
            protection_status=row["protection_status"],
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
        healthy = (
            heartbeat.screen_recording_permission
            and heartbeat.accessibility_permission
            and heartbeat.observer_healthy
        )
        protection_status = "PROTECTED" if healthy else "DEGRADED"
        with self.connect() as connection:
            cursor = connection.execute(
                """
                UPDATE devices SET last_seen_at = ?, protection_status = ?
                WHERE family_id = ? AND id = ? AND lifecycle_status = 'ACTIVE'
                """,
                (
                    heartbeat.observed_at.isoformat(),
                    protection_status,
                    family_id,
                    device_id,
                ),
            )
            if cursor.rowcount == 0:
                raise KeyError(device_id)
        return self.get_device(family_id, device_id)

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

    def unlock_incident(self, family_id: str, incident_id: str) -> Incident:
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
            now = _now_iso()
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
