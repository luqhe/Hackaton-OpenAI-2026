from __future__ import annotations

import hashlib
import json
import sqlite3
from collections.abc import Iterable, Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, Protocol


class MigrationPhase(StrEnum):
    EXPAND = "EXPAND"
    CONTRACT = "CONTRACT"


class MigrationRisk(StrEnum):
    LOW = "LOW"
    HIGH = "HIGH"


class SchemaDriftError(RuntimeError):
    pass


class UnsafeRollbackError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class Migration:
    identifier: str
    description: str
    phase: MigrationPhase
    risk: MigrationRisk
    depends_on: tuple[str, ...]
    up_statements: tuple[str, ...]
    down_statements: tuple[str, ...]
    non_empty_down_guards: tuple[str, ...] = ()

    @property
    def checksum(self) -> str:
        serialized = json.dumps(
            {
                "identifier": self.identifier,
                "description": self.description,
                "phase": self.phase,
                "risk": self.risk,
                "depends_on": self.depends_on,
                "up": self.up_statements,
                "down": self.down_statements,
                "guards": self.non_empty_down_guards,
            },
            ensure_ascii=True,
            separators=(",", ":"),
            sort_keys=True,
        )
        return hashlib.sha256(serialized.encode()).hexdigest()


class MigrationSession(Protocol):
    dialect: str

    def ensure_history(self) -> None: ...

    def applied(self) -> list[tuple[str, str]]: ...

    def execute(self, statement: str, parameters: Sequence[object] = ()) -> Any: ...

    def record_applied(self, migration: Migration) -> None: ...

    def remove_applied(self, identifier: str) -> None: ...

    def table_has_rows(self, table_name: str) -> bool: ...

    def transaction(self) -> Any: ...


class SQLiteMigrationSession:
    dialect = "sqlite"

    def __init__(self, connection: sqlite3.Connection):
        self.connection = connection

    def ensure_history(self) -> None:
        self.connection.execute(
            """
            CREATE TABLE IF NOT EXISTS guardian_schema_migrations (
                identifier TEXT PRIMARY KEY,
                checksum TEXT NOT NULL,
                applied_at TEXT NOT NULL
            )
            """
        )
        self.connection.commit()

    def applied(self) -> list[tuple[str, str]]:
        rows = self.connection.execute(
            "SELECT identifier, checksum FROM guardian_schema_migrations ORDER BY rowid"
        ).fetchall()
        return [(str(row[0]), str(row[1])) for row in rows]

    def execute(self, statement: str, parameters: Sequence[object] = ()) -> sqlite3.Cursor:
        return self.connection.execute(statement, parameters)

    def record_applied(self, migration: Migration) -> None:
        self.connection.execute(
            """
            INSERT INTO guardian_schema_migrations(identifier, checksum, applied_at)
            VALUES (?, ?, ?)
            """,
            (migration.identifier, migration.checksum, datetime.now(UTC).isoformat()),
        )

    def remove_applied(self, identifier: str) -> None:
        self.connection.execute("DELETE FROM guardian_schema_migrations WHERE identifier = ?", (identifier,))

    def table_has_rows(self, table_name: str) -> bool:
        if not table_name.replace("_", "").isalnum():
            raise ValueError("Invalid guarded table name")
        return self.connection.execute(f"SELECT 1 FROM {table_name} LIMIT 1").fetchone() is not None

    @contextmanager
    def transaction(self) -> Iterator[None]:
        try:
            self.connection.execute("BEGIN")
            yield
            self.connection.commit()
        except Exception:
            self.connection.rollback()
            raise


class PostgresMigrationSession:
    dialect = "postgresql"

    def __init__(self, connection: Any):
        self.connection = connection

    def ensure_history(self) -> None:
        self.connection.execute(
            """
            CREATE TABLE IF NOT EXISTS guardian_schema_migrations (
                identifier TEXT PRIMARY KEY,
                checksum TEXT NOT NULL,
                applied_at TIMESTAMPTZ NOT NULL
            )
            """
        )

    def applied(self) -> list[tuple[str, str]]:
        rows = self.connection.execute(
            "SELECT identifier, checksum FROM guardian_schema_migrations ORDER BY applied_at"
        ).fetchall()
        return [(str(row[0]), str(row[1])) for row in rows]

    def execute(self, statement: str, parameters: Sequence[object] = ()) -> Any:
        return self.connection.execute(statement, parameters)

    def record_applied(self, migration: Migration) -> None:
        self.connection.execute(
            """
            INSERT INTO guardian_schema_migrations(identifier, checksum, applied_at)
            VALUES (%s, %s, %s)
            """,
            (migration.identifier, migration.checksum, datetime.now(UTC)),
        )

    def remove_applied(self, identifier: str) -> None:
        self.connection.execute("DELETE FROM guardian_schema_migrations WHERE identifier = %s", (identifier,))

    def table_has_rows(self, table_name: str) -> bool:
        if not table_name.replace("_", "").isalnum():
            raise ValueError("Invalid guarded table name")
        return self.connection.execute(f"SELECT 1 FROM {table_name} LIMIT 1").fetchone() is not None

    def transaction(self) -> Any:
        return self.connection.transaction()


class MigrationRunner:
    def __init__(self, session: MigrationSession, migrations: Iterable[Migration]):
        self.session = session
        self.migrations = tuple(migrations)
        identifiers = [migration.identifier for migration in self.migrations]
        if len(identifiers) != len(set(identifiers)):
            raise ValueError("Migration identifiers must be unique")

    def applied_ids(self) -> list[str]:
        self.session.ensure_history()
        return [identifier for identifier, _ in self.session.applied()]

    def up(self) -> None:
        self.session.ensure_history()
        applied = dict(self.session.applied())
        manifest = {migration.identifier: migration for migration in self.migrations}
        unknown = set(applied) - set(manifest)
        if unknown:
            raise SchemaDriftError(f"Applied migrations are missing from manifest: {sorted(unknown)}")

        for identifier, checksum in applied.items():
            if manifest[identifier].checksum != checksum:
                raise SchemaDriftError(f"Migration {identifier} checksum does not match the manifest")

        for migration in self.migrations:
            if migration.identifier in applied:
                continue
            missing_dependencies = set(migration.depends_on) - (set(applied) | set(manifest))
            if missing_dependencies:
                raise SchemaDriftError(
                    f"Migration {migration.identifier} has missing dependencies: "
                    f"{sorted(missing_dependencies)}"
                )
            unapplied_dependencies = set(migration.depends_on) - set(applied)
            if unapplied_dependencies:
                raise SchemaDriftError(
                    f"Migration {migration.identifier} must follow: {sorted(unapplied_dependencies)}"
                )
            with self.session.transaction():
                for statement in migration.up_statements:
                    self.session.execute(statement)
                self.session.record_applied(migration)
            applied[migration.identifier] = migration.checksum

    def down(self, identifier: str) -> None:
        self.session.ensure_history()
        applied_order = [item for item, _ in self.session.applied()]
        if identifier not in applied_order:
            raise KeyError(identifier)
        if applied_order[-1] != identifier:
            raise UnsafeRollbackError("Only the most recently applied migration can be rolled back")
        migration = next(item for item in self.migrations if item.identifier == identifier)
        for table_name in migration.non_empty_down_guards:
            if self.session.table_has_rows(table_name):
                raise UnsafeRollbackError(f"Refusing to drop non-empty table {table_name}")
        with self.session.transaction():
            for statement in migration.down_statements:
                self.session.execute(statement)
            self.session.remove_applied(identifier)
