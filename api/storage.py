from __future__ import annotations

import hashlib
import json
import sqlite3
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

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
from guardian_core.version import SCHEMA_VERSION


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


SCHEMA = """
CREATE TABLE IF NOT EXISTS families (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS children (
    id TEXT PRIMARY KEY,
    family_id TEXT NOT NULL REFERENCES families(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS devices (
    id TEXT PRIMARY KEY,
    child_id TEXT NOT NULL REFERENCES children(id),
    name TEXT NOT NULL,
    platform TEXT NOT NULL,
    paired_at TEXT NOT NULL,
    last_seen_at TEXT,
    protection_status TEXT NOT NULL DEFAULT 'PROTECTED'
);

CREATE TABLE IF NOT EXISTS policies (
    child_id TEXT NOT NULL REFERENCES children(id),
    category TEXT NOT NULL,
    action TEXT NOT NULL,
    minimum_risk TEXT NOT NULL,
    minimum_confidence REAL NOT NULL,
    PRIMARY KEY (child_id, category)
);

CREATE TABLE IF NOT EXISTS incidents (
    id TEXT PRIMARY KEY,
    child_id TEXT NOT NULL REFERENCES children(id),
    device_id TEXT NOT NULL REFERENCES devices(id),
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
    UNIQUE(device_id, deduplication_key)
);

CREATE TABLE IF NOT EXISTS incident_evidence (
    id TEXT PRIMARY KEY,
    incident_id TEXT NOT NULL REFERENCES incidents(id) ON DELETE CASCADE,
    file_path TEXT NOT NULL,
    content_type TEXT NOT NULL,
    sha256 TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE(incident_id, sha256)
);

CREATE TABLE IF NOT EXISTS device_commands (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    device_id TEXT NOT NULL REFERENCES devices(id),
    incident_id TEXT NOT NULL REFERENCES incidents(id),
    command_type TEXT NOT NULL,
    application TEXT NOT NULL,
    status TEXT NOT NULL,
    created_at TEXT NOT NULL,
    acknowledged_at TEXT
);

CREATE TABLE IF NOT EXISTS app_sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    child_id TEXT NOT NULL REFERENCES children(id),
    app_name TEXT NOT NULL,
    observed_date TEXT NOT NULL,
    duration_seconds INTEGER NOT NULL CHECK (duration_seconds >= 0)
);

CREATE TABLE IF NOT EXISTS daily_telemetry (
    child_id TEXT NOT NULL REFERENCES children(id),
    observed_date TEXT NOT NULL,
    screen_changes INTEGER NOT NULL DEFAULT 0,
    media_sessions INTEGER NOT NULL DEFAULT 0,
    suspicious_events INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (child_id, observed_date)
);

CREATE TABLE IF NOT EXISTS pilot_onboarding_events (
    id TEXT PRIMARY KEY,
    child_id TEXT NOT NULL REFERENCES children(id) ON DELETE CASCADE,
    device_id TEXT REFERENCES devices(id) ON DELETE CASCADE,
    session_id TEXT NOT NULL,
    stage TEXT NOT NULL,
    occurred_at TEXT NOT NULL,
    idempotency_key TEXT NOT NULL UNIQUE,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS agent_health_samples (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    device_id TEXT NOT NULL REFERENCES devices(id) ON DELETE CASCADE,
    agent_version TEXT NOT NULL,
    screen_recording_permission INTEGER NOT NULL,
    accessibility_permission INTEGER NOT NULL,
    observer_healthy INTEGER NOT NULL,
    offline_queue_depth INTEGER NOT NULL,
    protection_status TEXT NOT NULL,
    observed_at TEXT NOT NULL,
    received_at TEXT NOT NULL
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

CREATE INDEX IF NOT EXISTS idx_incidents_child_occurred
ON incidents(child_id, occurred_at DESC);

CREATE INDEX IF NOT EXISTS idx_incidents_device_status
ON incidents(device_id, status);

CREATE INDEX IF NOT EXISTS idx_commands_device_pending
ON device_commands(device_id, id)
WHERE status = 'PENDING';

CREATE INDEX IF NOT EXISTS idx_sessions_child_date
ON app_sessions(child_id, observed_date);

CREATE UNIQUE INDEX IF NOT EXISTS idx_evidence_incident_sha256
ON incident_evidence(incident_id, sha256);

CREATE INDEX IF NOT EXISTS idx_pilot_onboarding_stage_time
ON pilot_onboarding_events(stage, occurred_at);

CREATE INDEX IF NOT EXISTS idx_agent_health_device_received
ON agent_health_samples(device_id, received_at DESC);
"""


class GuardianStore:
    def __init__(self, database_path: Path, evidence_directory: Path):
        self.database_path = database_path
        self.evidence_directory = evidence_directory

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
            connection.executescript(SCHEMA)
            now = _now_iso()
            self._ensure_family_schema(connection, now)
            demo_reference = self._family_reference("family-demo")
            demo_deleted = connection.execute(
                """
                SELECT 1 FROM family_deletion_receipts
                WHERE family_reference_sha256 = ? AND status = ?
                """,
                (demo_reference, FamilyDeletionStatus.COMPLETED),
            ).fetchone()
            if demo_deleted is None:
                connection.execute(
                    "INSERT OR IGNORE INTO families(id, name, created_at) VALUES (?, ?, ?)",
                    ("family-demo", "Família Demo", now),
                )
                connection.execute(
                    """
                    INSERT OR IGNORE INTO children(id, family_id, name, created_at)
                    VALUES (?, ?, ?, ?)
                    """,
                    ("child-demo", "family-demo", "Lucas", now),
                )
                connection.execute(
                    "UPDATE children SET family_id = ? WHERE family_id IS NULL",
                    ("family-demo",),
                )
                connection.execute(
                    """
                    INSERT OR IGNORE INTO devices(
                        id, child_id, name, platform, paired_at, last_seen_at, protection_status
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    ("device-demo", "child-demo", "MacBook Pro", "macOS", now, now, "PROTECTED"),
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
                            child_id, category, action, minimum_risk, minimum_confidence
                        ) VALUES (?, ?, ?, ?, ?)
                        """,
                        ("child-demo", category, action, RiskLevel.HIGH, confidence),
                    )
            connection.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
            connection.execute("CREATE INDEX IF NOT EXISTS idx_children_family ON children(family_id)")
            violations = connection.execute("PRAGMA foreign_key_check").fetchall()
            if violations:
                raise RuntimeError("Database migration left foreign-key violations")
            connection.execute("PRAGMA optimize")

    @staticmethod
    def _ensure_family_schema(connection: sqlite3.Connection, now: str) -> None:
        columns = {row["name"]: row for row in connection.execute("PRAGMA table_info(children)").fetchall()}
        has_family_id = "family_id" in columns
        if has_family_id:
            family_ids = [
                row["family_id"]
                for row in connection.execute(
                    "SELECT DISTINCT family_id FROM children WHERE family_id IS NOT NULL"
                ).fetchall()
            ]
            for family_id in family_ids:
                connection.execute(
                    "INSERT OR IGNORE INTO families(id, name, created_at) VALUES (?, ?, ?)",
                    (family_id, "Migrated family", now),
                )
        connection.execute(
            "INSERT OR IGNORE INTO families(id, name, created_at) VALUES (?, ?, ?)",
            ("family-demo", "Família Demo", now),
        )

        family_foreign_key = next(
            (
                row
                for row in connection.execute("PRAGMA foreign_key_list(children)").fetchall()
                if row["from"] == "family_id" and row["table"] == "families"
            ),
            None,
        )
        needs_rebuild = (
            not has_family_id
            or columns["family_id"]["notnull"] != 1
            or family_foreign_key is None
            or family_foreign_key["on_delete"].upper() != "CASCADE"
        )
        if not needs_rebuild:
            return

        family_expression = "COALESCE(family_id, 'family-demo')" if has_family_id else "'family-demo'"
        connection.commit()
        connection.execute("PRAGMA foreign_keys = OFF")
        try:
            connection.execute("DROP TABLE IF EXISTS children_v3")
            connection.execute(
                """
                CREATE TABLE children_v3 (
                    id TEXT PRIMARY KEY,
                    family_id TEXT NOT NULL REFERENCES families(id) ON DELETE CASCADE,
                    name TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
                """
            )
            connection.execute(
                f"""
                INSERT INTO children_v3(id, family_id, name, created_at)
                SELECT id, {family_expression}, name, created_at FROM children
                """
            )
            connection.execute("DROP TABLE children")
            connection.execute("ALTER TABLE children_v3 RENAME TO children")
            connection.commit()
        finally:
            connection.execute("PRAGMA foreign_keys = ON")

    @staticmethod
    def _family_reference(family_id: str) -> str:
        return hashlib.sha256(family_id.encode("utf-8")).hexdigest()

    def child_exists(self, child_id: str) -> bool:
        with self.connect() as connection:
            return (
                connection.execute("SELECT 1 FROM children WHERE id = ?", (child_id,)).fetchone() is not None
            )

    def device_exists(self, device_id: str) -> bool:
        with self.connect() as connection:
            return (
                connection.execute("SELECT 1 FROM devices WHERE id = ?", (device_id,)).fetchone() is not None
            )

    def pair_device(self, request: DevicePairRequest) -> Device:
        device_id = f"device-{uuid.uuid4().hex[:12]}"
        now = _now_iso()
        with self.connect() as connection:
            connection.execute(
                """
                INSERT INTO devices(id, child_id, name, platform, paired_at, last_seen_at, protection_status)
                VALUES (?, ?, ?, ?, ?, ?, 'PROTECTED')
                """,
                (device_id, request.child_id, request.device_name, request.platform, now, now),
            )
        return self.get_device(device_id)

    def get_device(self, device_id: str) -> Device:
        with self.connect() as connection:
            row = connection.execute("SELECT * FROM devices WHERE id = ?", (device_id,)).fetchone()
        if row is None:
            raise KeyError(device_id)
        return Device(
            id=row["id"],
            child_id=row["child_id"],
            name=row["name"],
            platform=row["platform"],
            paired_at=row["paired_at"],
            last_seen_at=row["last_seen_at"],
            protection_status=row["protection_status"],
        )

    def touch_device(self, device_id: str) -> None:
        with self.connect() as connection:
            cursor = connection.execute(
                "UPDATE devices SET last_seen_at = ?, protection_status = 'PROTECTED' WHERE id = ?",
                (_now_iso(), device_id),
            )
            if cursor.rowcount == 0:
                raise KeyError(device_id)

    def record_heartbeat(self, device_id: str, heartbeat: DeviceHeartbeat) -> Device:
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
                "UPDATE devices SET last_seen_at = ?, protection_status = ? WHERE id = ?",
                (heartbeat.observed_at.isoformat(), protection_status, device_id),
            )
            if cursor.rowcount == 0:
                raise KeyError(device_id)
            connection.execute(
                """
                INSERT INTO agent_health_samples(
                    device_id, agent_version, screen_recording_permission,
                    accessibility_permission, observer_healthy, offline_queue_depth,
                    protection_status, observed_at, received_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
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
        return self.get_device(device_id)

    def record_onboarding_event(self, event: PilotOnboardingEventCreate) -> tuple[PilotOnboardingEvent, bool]:
        event_id = f"onb-{uuid.uuid4().hex[:16]}"
        created_at = _now_iso()
        created = True
        with self.connect() as connection:
            child = connection.execute("SELECT 1 FROM children WHERE id = ?", (event.child_id,)).fetchone()
            if child is None:
                raise KeyError(event.child_id)
            if event.device_id is not None:
                device = connection.execute(
                    "SELECT child_id FROM devices WHERE id = ?", (event.device_id,)
                ).fetchone()
                if device is None:
                    raise KeyError(event.device_id)
                if device["child_id"] != event.child_id:
                    raise ValueError("Onboarding device does not belong to child")

            existing = connection.execute(
                """
                SELECT id, child_id, device_id, session_id, stage, occurred_at
                FROM pilot_onboarding_events WHERE idempotency_key = ?
                """,
                (event.idempotency_key,),
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
                return self.get_onboarding_event(event_id), created

            session_rows = connection.execute(
                """
                SELECT child_id, device_id, stage, occurred_at
                FROM pilot_onboarding_events
                WHERE session_id = ?
                ORDER BY created_at, id
                """,
                (event.session_id,),
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
                        id, child_id, device_id, session_id, stage, occurred_at,
                        idempotency_key, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        event_id,
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
                    FROM pilot_onboarding_events WHERE idempotency_key = ?
                    """,
                    (event.idempotency_key,),
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
        return self.get_onboarding_event(event_id), created

    def get_onboarding_event(self, event_id: str) -> PilotOnboardingEvent:
        with self.connect() as connection:
            row = connection.execute(
                """
                SELECT id, child_id, device_id, session_id, stage, occurred_at, created_at
                FROM pilot_onboarding_events WHERE id = ?
                """,
                (event_id,),
            ).fetchone()
        if row is None:
            raise KeyError(event_id)
        return PilotOnboardingEvent(**dict(row))

    @staticmethod
    def _placeholders(values: list[str]) -> str:
        return ",".join("?" for _ in values)

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
                    staged = staging_directory / source.name
                    source.replace(staged)
                    staged_files.append((source, staged))
                self._set_deletion_status(
                    receipt_id,
                    FamilyDeletionStatus.STARTED,
                    staging_directory=staging_directory,
                )
        except OSError as error:
            for source, staged in staged_files:
                if staged.is_file():
                    staged.replace(source)
            if staging_directory.is_dir():
                try:
                    staging_directory.rmdir()
                except OSError:
                    pass
            self._set_deletion_status(
                receipt_id,
                FamilyDeletionStatus.FAILED_STORAGE_CLEANUP,
                staging_directory=staging_directory if staging_directory.exists() else None,
            )
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
                    try:
                        staged.replace(source)
                    except OSError as restore_error:
                        restore_errors.append(restore_error)
            if staging_directory.is_dir():
                try:
                    staging_directory.rmdir()
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
                staging_directory.rmdir()
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

        entries = list(staging_directory.iterdir()) if staging_directory.is_dir() else []
        for entry in entries:
            if entry.is_symlink() or not entry.is_file() or entry.resolve().parent != staging_directory:
                raise ValueError("Deletion staging contains an unsupported entry")

        if status == FamilyDeletionStatus.FAILED_DATABASE:
            for staged in entries:
                destination = evidence_root / staged.name
                if destination.exists():
                    raise FileExistsError(f"Refusing to overwrite restored evidence {destination.name}")
                staged.replace(destination)
            terminal_status = FamilyDeletionStatus.FAILED_DATABASE
            completed_at = None
        else:
            for staged in entries:
                staged.unlink()
            terminal_status = FamilyDeletionStatus.COMPLETED
            completed_at = _now_iso()

        if staging_directory.is_dir():
            staging_directory.rmdir()
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

    def pilot_metrics(self, since_hours: int) -> PilotMetricsReport:
        generated_at = datetime.now(UTC)
        window_started_at = generated_at - timedelta(hours=since_hours)
        window_start = window_started_at.isoformat()
        with self.connect() as connection:
            funnel_rows = connection.execute(
                """
                SELECT stage, COUNT(*) AS event_count,
                       COUNT(DISTINCT session_id) AS unique_sessions
                FROM pilot_onboarding_events
                WHERE occurred_at >= ?
                GROUP BY stage
                """,
                (window_start,),
            ).fetchall()
            health_rows = connection.execute(
                """
                SELECT device_id, protection_status, offline_queue_depth, observed_at
                FROM agent_health_samples
                WHERE received_at >= ?
                ORDER BY received_at
                """,
                (window_start,),
            ).fetchall()
            command_rows = connection.execute(
                """
                SELECT created_at, acknowledged_at
                FROM device_commands
                WHERE acknowledged_at IS NOT NULL AND created_at >= ?
                """,
                (window_start,),
            ).fetchall()
            deletion_failures = connection.execute(
                """
                SELECT COUNT(*) AS total FROM family_deletion_receipts
                WHERE requested_at >= ? AND status IN (?, ?)
                """,
                (
                    window_start,
                    FamilyDeletionStatus.FAILED_DATABASE,
                    FamilyDeletionStatus.FAILED_STORAGE_CLEANUP,
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

    def get_policy(self, child_id: str) -> list[PolicyRule]:
        with self.connect() as connection:
            rows = connection.execute(
                "SELECT category, action, minimum_risk, minimum_confidence FROM policies WHERE child_id = ? ORDER BY category",
                (child_id,),
            ).fetchall()
        return [PolicyRule(**dict(row)) for row in rows]

    def replace_policy(self, child_id: str, rules: list[PolicyRule]) -> list[PolicyRule]:
        with self.connect() as connection:
            connection.execute("DELETE FROM policies WHERE child_id = ?", (child_id,))
            connection.executemany(
                """
                INSERT INTO policies(child_id, category, action, minimum_risk, minimum_confidence)
                VALUES (?, ?, ?, ?, ?)
                """,
                [
                    (child_id, rule.category, rule.action, rule.minimum_risk, rule.minimum_confidence)
                    for rule in rules
                ],
            )
        return self.get_policy(child_id)

    def create_incident(self, request: IncidentCreate) -> tuple[Incident, bool]:
        if request.assessment.category is None or request.assessment.direction is None:
            raise ValueError("SAFE assessments cannot create incidents")

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
                id, child_id, device_id, application, occurred_at, category, direction,
                severity, confidence, explanation, evidence_json, policy_action, status,
                deduplication_key, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        with self.connect() as connection:
            try:
                connection.execute(insert_sql, values(request.deduplication_key))
            except sqlite3.IntegrityError as error:
                duplicate = connection.execute(
                    "SELECT id, status FROM incidents WHERE device_id = ? AND deduplication_key = ?",
                    (request.device_id, request.deduplication_key),
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
        return self.get_incident(incident_id), created

    def _incident_from_row(self, row: sqlite3.Row, screenshot_urls: list[str]) -> Incident:
        return Incident(
            id=row["id"],
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

    def get_incident(self, incident_id: str) -> Incident:
        with self.connect() as connection:
            row = connection.execute("SELECT * FROM incidents WHERE id = ?", (incident_id,)).fetchone()
            evidence_rows = connection.execute(
                "SELECT id FROM incident_evidence WHERE incident_id = ? ORDER BY created_at",
                (incident_id,),
            ).fetchall()
        if row is None:
            raise KeyError(incident_id)
        urls = [f"/api/evidence/{item['id']}" for item in evidence_rows]
        return self._incident_from_row(row, urls)

    def list_incidents(
        self, child_id: str, limit: int, status: IncidentStatus | None = None
    ) -> list[Incident]:
        sql = "SELECT id FROM incidents WHERE child_id = ?"
        parameters: list[object] = [child_id]
        if status is not None:
            sql += " AND status = ?"
            parameters.append(status)
        sql += " ORDER BY occurred_at DESC LIMIT ?"
        parameters.append(limit)
        with self.connect() as connection:
            rows = connection.execute(sql, parameters).fetchall()
        return [self.get_incident(row["id"]) for row in rows]

    def request_unlock(self, incident_id: str, explanation: str) -> Incident:
        with self.connect() as connection:
            row = connection.execute("SELECT status FROM incidents WHERE id = ?", (incident_id,)).fetchone()
            if row is None:
                raise KeyError(incident_id)
            if row["status"] not in (IncidentStatus.BLOCKED, IncidentStatus.UNLOCK_REQUESTED):
                raise ValueError(f"Cannot request unlock from status {row['status']}")
            connection.execute(
                """
                UPDATE incidents
                SET status = ?, child_explanation = ?, updated_at = ?
                WHERE id = ?
                """,
                (IncidentStatus.UNLOCK_REQUESTED, explanation, _now_iso(), incident_id),
            )
        return self.get_incident(incident_id)

    def unlock_incident(self, incident_id: str) -> Incident:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT status, device_id, application FROM incidents WHERE id = ?",
                (incident_id,),
            ).fetchone()
            if row is None:
                raise KeyError(incident_id)
            if row["status"] == IncidentStatus.UNLOCKED:
                return self.get_incident(incident_id)
            if row["status"] not in (IncidentStatus.BLOCKED, IncidentStatus.UNLOCK_REQUESTED):
                raise ValueError(f"Cannot unlock incident from status {row['status']}")
            now = _now_iso()
            connection.execute(
                "UPDATE incidents SET status = ?, updated_at = ? WHERE id = ?",
                (IncidentStatus.UNLOCKED, now, incident_id),
            )
            connection.execute(
                """
                INSERT INTO device_commands(
                    device_id, incident_id, command_type, application, status, created_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    row["device_id"],
                    incident_id,
                    CommandType.UNLOCK_APPLICATION,
                    row["application"],
                    CommandStatus.PENDING,
                    now,
                ),
            )
        return self.get_incident(incident_id)

    def keep_blocked(self, incident_id: str) -> Incident:
        with self.connect() as connection:
            row = connection.execute("SELECT status FROM incidents WHERE id = ?", (incident_id,)).fetchone()
            if row is None:
                raise KeyError(incident_id)
            if row["status"] not in (IncidentStatus.BLOCKED, IncidentStatus.UNLOCK_REQUESTED):
                raise ValueError(f"Cannot keep blocked from status {row['status']}")
            connection.execute(
                "UPDATE incidents SET status = ?, updated_at = ? WHERE id = ?",
                (IncidentStatus.KEPT_BLOCKED, _now_iso(), incident_id),
            )
        return self.get_incident(incident_id)

    def save_evidence(self, incident_id: str, data: bytes, content_type: str) -> str:
        self.get_incident(incident_id)
        suffixes = {"image/png": ".png", "image/jpeg": ".jpg", "image/webp": ".webp", "text/plain": ".txt"}
        suffix = suffixes[content_type]
        digest = hashlib.sha256(data).hexdigest()
        with self.connect() as connection:
            existing = connection.execute(
                "SELECT id FROM incident_evidence WHERE incident_id = ? AND sha256 = ?",
                (incident_id, digest),
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
                    INSERT INTO incident_evidence(id, incident_id, file_path, content_type, sha256, created_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        evidence_id,
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

    def get_evidence(self, evidence_id: str) -> tuple[Path, str]:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT file_path, content_type FROM incident_evidence WHERE id = ?",
                (evidence_id,),
            ).fetchone()
        if row is None:
            raise KeyError(evidence_id)
        path = Path(row["file_path"]).resolve()
        evidence_root = self.evidence_directory.resolve()
        if evidence_root not in path.parents or not path.is_file():
            raise FileNotFoundError(evidence_id)
        return path, row["content_type"]

    def pending_commands(self, device_id: str, after_id: int) -> list[DeviceCommand]:
        self.touch_device(device_id)
        with self.connect() as connection:
            rows = connection.execute(
                """
                SELECT id, device_id, incident_id, command_type AS type, application, status,
                       created_at, acknowledged_at
                FROM device_commands
                WHERE device_id = ? AND status = ? AND id > ?
                ORDER BY id
                """,
                (device_id, CommandStatus.PENDING, after_id),
            ).fetchall()
        return [DeviceCommand(**dict(row)) for row in rows]

    def acknowledge_command(self, device_id: str, command_id: int) -> DeviceCommand:
        with self.connect() as connection:
            cursor = connection.execute(
                """
                UPDATE device_commands
                SET status = ?, acknowledged_at = ?
                WHERE id = ? AND device_id = ? AND status = ?
                """,
                (CommandStatus.ACKNOWLEDGED, _now_iso(), command_id, device_id, CommandStatus.PENDING),
            )
            if cursor.rowcount == 0:
                existing = connection.execute(
                    "SELECT 1 FROM device_commands WHERE id = ? AND device_id = ?",
                    (command_id, device_id),
                ).fetchone()
                if existing is None:
                    raise KeyError(command_id)
            row = connection.execute(
                """
                SELECT id, device_id, incident_id, command_type AS type, application, status,
                       created_at, acknowledged_at
                FROM device_commands WHERE id = ?
                """,
                (command_id,),
            ).fetchone()
        return DeviceCommand(**dict(row))

    def record_telemetry(self, device_id: str, update: TelemetryUpdate) -> None:
        self.touch_device(device_id)
        observed_date = update.observed_at.date().isoformat()
        with self.connect() as connection:
            if update.app_name and update.session_seconds:
                connection.execute(
                    "INSERT INTO app_sessions(child_id, app_name, observed_date, duration_seconds) VALUES (?, ?, ?, ?)",
                    (update.child_id, update.app_name, observed_date, update.session_seconds),
                )
            connection.execute(
                """
                INSERT INTO daily_telemetry(
                    child_id, observed_date, screen_changes, media_sessions, suspicious_events
                ) VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(child_id, observed_date) DO UPDATE SET
                    screen_changes = screen_changes + excluded.screen_changes,
                    media_sessions = media_sessions + excluded.media_sessions,
                    suspicious_events = suspicious_events + excluded.suspicious_events
                """,
                (
                    update.child_id,
                    observed_date,
                    update.screen_changes,
                    update.media_sessions,
                    update.suspicious_events,
                ),
            )

    def daily_report(self, child_id: str, report_date: date) -> DailyReport:
        date_value = report_date.isoformat()
        with self.connect() as connection:
            child = connection.execute("SELECT name FROM children WHERE id = ?", (child_id,)).fetchone()
            if child is None:
                raise KeyError(child_id)
            apps = connection.execute(
                """
                SELECT app_name AS app, SUM(duration_seconds) AS seconds
                FROM app_sessions
                WHERE child_id = ? AND observed_date = ?
                GROUP BY app_name
                ORDER BY seconds DESC
                """,
                (child_id, date_value),
            ).fetchall()
            incident_counts = connection.execute(
                """
                SELECT COUNT(*) AS incident_count,
                       SUM(CASE WHEN policy_action = 'BLOCK' THEN 1 ELSE 0 END) AS interventions
                FROM incidents
                WHERE child_id = ? AND substr(occurred_at, 1, 10) = ?
                """,
                (child_id, date_value),
            ).fetchone()
            telemetry = connection.execute(
                """
                SELECT screen_changes, media_sessions, suspicious_events
                FROM daily_telemetry WHERE child_id = ? AND observed_date = ?
                """,
                (child_id, date_value),
            ).fetchone()
            evidence_count = connection.execute(
                """
                SELECT COUNT(*) AS total
                FROM incident_evidence evidence
                JOIN incidents incident ON incident.id = evidence.incident_id
                WHERE incident.child_id = ? AND substr(incident.occurred_at, 1, 10) = ?
                """,
                (child_id, date_value),
            ).fetchone()["total"]
        usage = [DailyAppUsage(**dict(row)) for row in apps]
        return DailyReport(
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
