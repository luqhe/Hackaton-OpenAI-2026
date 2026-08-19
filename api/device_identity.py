from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
import sqlite3
import uuid
from collections.abc import Callable
from datetime import UTC, datetime, timedelta

from api.storage import GuardianStore
from guardian_core.device_api import (
    CommandAcknowledgement,
    CommandExecutionResult,
    DeviceCredentialIssued,
    PairingConfirmation,
)
from guardian_core.device_protocol import (
    DEVICE_PROTOCOL_VERSION,
    CredentialRecord,
    DeviceCredentialStatus,
    DevicePrincipal,
)
from guardian_core.identity import FamilyScope
from guardian_core.models import CommandStatus, DeviceCommand

PAIRING_TTL = timedelta(minutes=10)
CREDENTIAL_TTL = timedelta(days=90)
ROTATION_GRACE = timedelta(minutes=5)
COMMAND_TTL = timedelta(minutes=10)
PAIRING_ALPHABET = "23456789ABCDEFGHJKLMNPQRSTUVWXYZ"
MAX_PAIRING_ATTEMPTS = 5
MAX_COMMAND_ATTEMPTS = 8

DEVICE_SCHEMA = """
CREATE TABLE IF NOT EXISTS pairing_challenges (
    id TEXT PRIMARY KEY,
    family_id TEXT NOT NULL,
    child_id TEXT NOT NULL,
    code_digest TEXT NOT NULL,
    created_at TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    consumed_at TEXT,
    failed_attempts INTEGER NOT NULL DEFAULT 0,
    FOREIGN KEY (family_id, child_id) REFERENCES children(family_id, id) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS device_credentials (
    credential_id TEXT PRIMARY KEY,
    family_id TEXT NOT NULL,
    child_id TEXT NOT NULL,
    device_id TEXT NOT NULL,
    public_key TEXT NOT NULL UNIQUE,
    status TEXT NOT NULL CHECK (status IN ('ACTIVE', 'ROTATING', 'REVOKED')),
    issued_at TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    revoked_at TEXT,
    rotated_from TEXT REFERENCES device_credentials(credential_id),
    FOREIGN KEY (family_id, child_id, device_id)
        REFERENCES devices(family_id, child_id, id) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS device_installations (
    installation_id TEXT PRIMARY KEY,
    device_id TEXT NOT NULL REFERENCES devices(id) ON DELETE CASCADE,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS device_request_nonces (
    credential_id TEXT NOT NULL REFERENCES device_credentials(credential_id) ON DELETE CASCADE,
    nonce TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    PRIMARY KEY (credential_id, nonce)
);
CREATE TABLE IF NOT EXISTS credential_rotations (
    old_credential_id TEXT NOT NULL REFERENCES device_credentials(credential_id),
    idempotency_key TEXT NOT NULL,
    new_credential_id TEXT NOT NULL UNIQUE REFERENCES device_credentials(credential_id),
    PRIMARY KEY (old_credential_id, idempotency_key)
);
CREATE INDEX IF NOT EXISTS idx_pairing_expiry ON pairing_challenges(expires_at);
CREATE INDEX IF NOT EXISTS idx_device_credentials_device ON device_credentials(device_id, status);
CREATE INDEX IF NOT EXISTS idx_device_nonces_expiry ON device_request_nonces(expires_at);
"""


class PairingError(ValueError):
    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


class DeviceIdentityStore:
    def __init__(
        self,
        store: GuardianStore,
        *,
        pairing_pepper: bytes,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ):
        if len(pairing_pepper) < 32:
            raise ValueError("pairing pepper must contain at least 32 bytes")
        self.store = store
        self.pairing_pepper = pairing_pepper
        self.clock = clock

    def initialize(self) -> None:
        with self.store.connect() as connection:
            connection.executescript(DEVICE_SCHEMA)
            existing = {row[1] for row in connection.execute("PRAGMA table_info(device_commands)")}
            additions = {
                "protocol_version": "TEXT NOT NULL DEFAULT '1.0'",
                "idempotency_key": "TEXT",
                "expires_at": "TEXT",
                "attempt_count": "INTEGER NOT NULL DEFAULT 0",
                "delivered_at": "TEXT",
                "next_attempt_at": "TEXT",
                "terminal_error": "TEXT",
            }
            for column, definition in additions.items():
                if column not in existing:
                    connection.execute(f"ALTER TABLE device_commands ADD COLUMN {column} {definition}")
            connection.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS idx_command_idempotency "
                "ON device_commands(device_id, idempotency_key) WHERE idempotency_key IS NOT NULL"
            )

    def _pairing_digest(self, challenge_id: str, code: str) -> str:
        normalized = code.replace("-", "").upper()
        return hmac.new(
            self.pairing_pepper,
            f"{challenge_id}:{normalized}".encode("ascii"),
            hashlib.sha256,
        ).hexdigest()

    def create_pairing_challenge(self, scope: FamilyScope, child_id: str) -> dict[str, object]:
        now = self.clock()
        challenge_id = f"pair-{secrets.token_urlsafe(18)}"
        raw_code = "".join(secrets.choice(PAIRING_ALPHABET) for _ in range(8))
        code = f"{raw_code[:4]}-{raw_code[4:]}"
        with self.store.connect() as connection:
            child = connection.execute(
                "SELECT 1 FROM children WHERE family_id = ? AND id = ?",
                (scope.family_id, child_id),
            ).fetchone()
            if child is None:
                raise KeyError(child_id)
            connection.execute(
                """
                INSERT INTO pairing_challenges(
                    id, family_id, child_id, code_digest, created_at, expires_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    challenge_id,
                    scope.family_id,
                    child_id,
                    self._pairing_digest(challenge_id, code),
                    now.isoformat(),
                    (now + PAIRING_TTL).isoformat(),
                ),
            )
        return {"challenge_id": challenge_id, "code": code, "expires_at": now + PAIRING_TTL}

    @staticmethod
    def _validate_public_key(value: str) -> None:
        try:
            decoded = base64.b64decode(value + "=", altchars=b"-_", validate=True)
        except ValueError as error:
            raise PairingError("invalid_pairing") from error
        if len(decoded) != 32:
            raise PairingError("invalid_pairing")

    def complete_pairing(self, request: PairingConfirmation) -> DeviceCredentialIssued:
        self._validate_public_key(request.public_key)
        now = self.clock()
        supplied_digest = self._pairing_digest(request.challenge_id, request.code)
        device_id = f"device-{uuid.uuid4().hex[:16]}"
        credential_id = f"cred-{secrets.token_urlsafe(18)}"
        with self.store.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            challenge = connection.execute(
                "SELECT * FROM pairing_challenges WHERE id = ?", (request.challenge_id,)
            ).fetchone()
            invalid = (
                challenge is None
                or challenge["consumed_at"] is not None
                or datetime.fromisoformat(challenge["expires_at"]) <= now
                or challenge["failed_attempts"] >= MAX_PAIRING_ATTEMPTS
            )
            if invalid:
                raise PairingError("invalid_or_expired_pairing")
            if not secrets.compare_digest(challenge["code_digest"], supplied_digest):
                connection.execute(
                    "UPDATE pairing_challenges SET failed_attempts = failed_attempts + 1 WHERE id = ?",
                    (request.challenge_id,),
                )
                connection.commit()
                raise PairingError("invalid_or_expired_pairing")
            previous = connection.execute(
                "SELECT device_id FROM device_installations WHERE installation_id = ?",
                (request.installation_id,),
            ).fetchone()
            if previous is not None:
                connection.execute(
                    "UPDATE device_credentials SET status = 'REVOKED', revoked_at = ? "
                    "WHERE device_id = ? AND status != 'REVOKED'",
                    (now.isoformat(), previous["device_id"]),
                )
                connection.execute(
                    "UPDATE devices SET lifecycle_status = 'REVOKED' WHERE id = ?",
                    (previous["device_id"],),
                )
            connection.execute(
                """
                INSERT INTO devices(
                    id, family_id, child_id, name, platform, paired_at, last_seen_at,
                    lifecycle_status
                ) VALUES (?, ?, ?, ?, ?, ?, NULL, 'ACTIVE')
                """,
                (
                    device_id,
                    challenge["family_id"],
                    challenge["child_id"],
                    request.device_name,
                    request.platform,
                    now.isoformat(),
                ),
            )
            expires_at = now + CREDENTIAL_TTL
            connection.execute(
                """
                INSERT INTO device_credentials(
                    credential_id, family_id, child_id, device_id, public_key,
                    status, issued_at, expires_at
                ) VALUES (?, ?, ?, ?, ?, 'ACTIVE', ?, ?)
                """,
                (
                    credential_id,
                    challenge["family_id"],
                    challenge["child_id"],
                    device_id,
                    request.public_key,
                    now.isoformat(),
                    expires_at.isoformat(),
                ),
            )
            connection.execute(
                """
                INSERT INTO device_installations(installation_id, device_id, updated_at)
                VALUES (?, ?, ?)
                ON CONFLICT(installation_id) DO UPDATE SET
                    device_id = excluded.device_id, updated_at = excluded.updated_at
                """,
                (request.installation_id, device_id, now.isoformat()),
            )
            connection.execute(
                "UPDATE pairing_challenges SET consumed_at = ? WHERE id = ? AND consumed_at IS NULL",
                (now.isoformat(), request.challenge_id),
            )
        return DeviceCredentialIssued(
            credential_id=credential_id,
            device_id=device_id,
            expires_at=expires_at,
            protocol_version=DEVICE_PROTOCOL_VERSION,
        )

    def get_credential(self, credential_id: str) -> CredentialRecord | None:
        with self.store.connect() as connection:
            row = connection.execute(
                """
                SELECT credential.*, device.lifecycle_status
                FROM device_credentials credential
                JOIN devices device ON device.id = credential.device_id
                WHERE credential.credential_id = ?
                """,
                (credential_id,),
            ).fetchone()
        if row is None:
            return None
        status = row["status"]
        if row["lifecycle_status"] == "REVOKED":
            status = DeviceCredentialStatus.REVOKED
        return CredentialRecord(
            credential_id=row["credential_id"],
            device_id=row["device_id"],
            family_id=row["family_id"],
            child_id=row["child_id"],
            public_key=row["public_key"],
            status=status,
            expires_at=datetime.fromisoformat(row["expires_at"]),
        )

    def consume(self, credential_id: str, nonce: str, expires_at: datetime) -> bool:
        with self.store.connect() as connection:
            connection.execute(
                "DELETE FROM device_request_nonces WHERE expires_at <= ?", (self.clock().isoformat(),)
            )
            try:
                connection.execute(
                    "INSERT INTO device_request_nonces(credential_id, nonce, expires_at) VALUES (?, ?, ?)",
                    (credential_id, nonce, expires_at.isoformat()),
                )
            except sqlite3.IntegrityError:
                return False
        return True

    def revoke_device(self, scope: FamilyScope, device_id: str) -> None:
        now = self.clock().isoformat()
        with self.store.connect() as connection:
            cursor = connection.execute(
                "UPDATE devices SET lifecycle_status = 'REVOKED' WHERE family_id = ? AND id = ?",
                (scope.family_id, device_id),
            )
            if cursor.rowcount == 0:
                raise KeyError(device_id)
            connection.execute(
                "UPDATE device_credentials SET status = 'REVOKED', revoked_at = ? "
                "WHERE family_id = ? AND device_id = ? AND status != 'REVOKED'",
                (now, scope.family_id, device_id),
            )

    def rotate_credential(
        self, principal: DevicePrincipal, public_key: str, idempotency_key: str
    ) -> DeviceCredentialIssued:
        self._validate_public_key(public_key)
        now = self.clock()
        with self.store.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            existing = connection.execute(
                """
                SELECT credential.* FROM credential_rotations rotation
                JOIN device_credentials credential
                    ON credential.credential_id = rotation.new_credential_id
                WHERE rotation.old_credential_id = ? AND rotation.idempotency_key = ?
                """,
                (principal.credential_id, idempotency_key),
            ).fetchone()
            if existing is not None:
                if not secrets.compare_digest(existing["public_key"], public_key):
                    raise PairingError("idempotency_conflict")
                return DeviceCredentialIssued(
                    credential_id=existing["credential_id"],
                    device_id=existing["device_id"],
                    expires_at=existing["expires_at"],
                    protocol_version=DEVICE_PROTOCOL_VERSION,
                )
            new_id = f"cred-{secrets.token_urlsafe(18)}"
            expires_at = now + CREDENTIAL_TTL
            connection.execute(
                "UPDATE device_credentials SET status = 'ROTATING', expires_at = ? "
                "WHERE credential_id = ? AND status = 'ACTIVE'",
                ((now + ROTATION_GRACE).isoformat(), principal.credential_id),
            )
            connection.execute(
                """
                INSERT INTO device_credentials(
                    credential_id, family_id, child_id, device_id, public_key,
                    status, issued_at, expires_at, rotated_from
                ) VALUES (?, ?, ?, ?, ?, 'ACTIVE', ?, ?, ?)
                """,
                (
                    new_id,
                    principal.family_id,
                    principal.child_id,
                    principal.device_id,
                    public_key,
                    now.isoformat(),
                    expires_at.isoformat(),
                    principal.credential_id,
                ),
            )
            connection.execute(
                "INSERT INTO credential_rotations VALUES (?, ?, ?)",
                (principal.credential_id, idempotency_key, new_id),
            )
        return DeviceCredentialIssued(
            credential_id=new_id,
            device_id=principal.device_id,
            expires_at=expires_at,
            protocol_version=DEVICE_PROTOCOL_VERSION,
        )

    def incident_belongs_to_device(self, principal: DevicePrincipal, incident_id: str) -> bool:
        with self.store.connect() as connection:
            return (
                connection.execute(
                    "SELECT 1 FROM incidents WHERE family_id = ? AND device_id = ? AND id = ?",
                    (principal.family_id, principal.device_id, incident_id),
                ).fetchone()
                is not None
            )

    def _prepare_commands(self, connection: sqlite3.Connection) -> None:
        rows = connection.execute(
            "SELECT id, incident_id, created_at FROM device_commands WHERE expires_at IS NULL"
        ).fetchall()
        for row in rows:
            created_at = datetime.fromisoformat(row["created_at"])
            connection.execute(
                "UPDATE device_commands SET protocol_version = ?, idempotency_key = ?, "
                "expires_at = ?, next_attempt_at = created_at WHERE id = ?",
                (
                    DEVICE_PROTOCOL_VERSION,
                    f"unlock:{row['incident_id']}",
                    (created_at + COMMAND_TTL).isoformat(),
                    row["id"],
                ),
            )

    @staticmethod
    def _command_from_row(row: sqlite3.Row) -> DeviceCommand:
        return DeviceCommand(
            id=row["id"],
            device_id=row["device_id"],
            incident_id=row["incident_id"],
            type=row["command_type"],
            application=row["application"],
            status=row["status"],
            created_at=row["created_at"],
            protocol_version=row["protocol_version"],
            idempotency_key=row["idempotency_key"],
            expires_at=row["expires_at"],
            attempt_count=row["attempt_count"],
            delivered_at=row["delivered_at"],
            next_attempt_at=row["next_attempt_at"],
            terminal_error=row["terminal_error"],
            acknowledged_at=row["acknowledged_at"],
        )

    def pending_commands(self, principal: DevicePrincipal, after_id: int) -> list[DeviceCommand]:
        now = self.clock()
        with self.store.connect() as connection:
            self._prepare_commands(connection)
            connection.execute(
                "UPDATE device_commands SET status = 'EXPIRED', terminal_error = 'COMMAND_EXPIRED' "
                "WHERE device_id = ? AND status IN ('PENDING', 'DELIVERED') AND expires_at <= ?",
                (principal.device_id, now.isoformat()),
            )
            connection.execute(
                "UPDATE device_commands SET status = 'FAILED', terminal_error = 'RETRY_EXHAUSTED' "
                "WHERE device_id = ? AND status = 'DELIVERED' AND attempt_count >= ?",
                (principal.device_id, MAX_COMMAND_ATTEMPTS),
            )
            rows = connection.execute(
                """
                SELECT * FROM device_commands
                WHERE family_id = ? AND device_id = ?
                  AND status IN ('PENDING', 'DELIVERED')
                  AND (id > ? OR status = 'DELIVERED')
                  AND (next_attempt_at IS NULL OR next_attempt_at <= ?)
                ORDER BY CASE command_type WHEN 'UNLOCK_APPLICATION' THEN 0 ELSE 1 END, id
                LIMIT 20
                """,
                (principal.family_id, principal.device_id, after_id, now.isoformat()),
            ).fetchall()
            delivered: list[DeviceCommand] = []
            for row in rows:
                attempt = row["attempt_count"] + 1
                delay = min(2 ** (attempt - 1), 30)
                connection.execute(
                    "UPDATE device_commands SET status = 'DELIVERED', attempt_count = ?, "
                    "delivered_at = ?, next_attempt_at = ? WHERE id = ?",
                    (attempt, now.isoformat(), (now + timedelta(seconds=delay)).isoformat(), row["id"]),
                )
                updated = connection.execute(
                    "SELECT * FROM device_commands WHERE id = ?", (row["id"],)
                ).fetchone()
                delivered.append(self._command_from_row(updated))
        return delivered

    def acknowledge_command(
        self, principal: DevicePrincipal, command_id: int, acknowledgement: CommandAcknowledgement
    ) -> DeviceCommand:
        with self.store.connect() as connection:
            self._prepare_commands(connection)
            row = connection.execute(
                "SELECT * FROM device_commands WHERE family_id = ? AND device_id = ? AND id = ?",
                (principal.family_id, principal.device_id, command_id),
            ).fetchone()
            if row is None:
                raise KeyError(command_id)
            if row["status"] in {CommandStatus.ACKNOWLEDGED, CommandStatus.FAILED}:
                return self._command_from_row(row)
            status = (
                CommandStatus.ACKNOWLEDGED
                if acknowledgement.result == CommandExecutionResult.EXECUTED
                else CommandStatus.FAILED
            )
            error_code = acknowledgement.error_code if status == CommandStatus.FAILED else None
            connection.execute(
                "UPDATE device_commands SET status = ?, acknowledged_at = ?, terminal_error = ? WHERE id = ?",
                (status, self.clock().isoformat(), error_code, command_id),
            )
            updated = connection.execute(
                "SELECT * FROM device_commands WHERE id = ?", (command_id,)
            ).fetchone()
        return self._command_from_row(updated)
