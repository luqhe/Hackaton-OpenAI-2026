from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path

import pytest

from api.data_security.config import DatabaseConfig, DataSecuritySettings
from api.data_security.database import PostgresDatabase, SQLiteDatabase, create_database
from guardian_core.config import Environment


def test_development_defaults_to_sqlite_but_staging_requires_postgres() -> None:
    settings = DataSecuritySettings.from_env({"GUARDIAN_ENVIRONMENT": "development"})

    assert settings.database.url.startswith("sqlite:///")

    with pytest.raises(ValueError, match="PostgreSQL"):
        DataSecuritySettings.from_env(
            {
                "GUARDIAN_ENVIRONMENT": "staging",
                "GUARDIAN_DATABASE_URL": "sqlite:////tmp/guardian.db",
            }
        )


@pytest.mark.parametrize(
    "url",
    [
        "postgresql://guardian:secret@db.internal/guardian",
        "postgresql://guardian:secret@db.internal/guardian?sslmode=require",
        "postgresql://guardian:secret@db.internal/guardian?sslmode=verify-ca",
    ],
)
def test_staging_rejects_postgres_without_verified_tls(url: str) -> None:
    with pytest.raises(ValueError, match="sslmode=verify-full"):
        DataSecuritySettings.from_env({"GUARDIAN_ENVIRONMENT": "staging", "GUARDIAN_DATABASE_URL": url})


def test_pool_bounds_are_validated() -> None:
    with pytest.raises(ValueError, match="pool"):
        DatabaseConfig(
            environment=Environment.PRODUCTION,
            url="postgresql://guardian:secret@db.internal/guardian?sslmode=verify-full",
            pool_min_size=9,
            pool_max_size=8,
        ).validate()


class _FakeConnection:
    def __init__(self) -> None:
        self.transaction_entries = 0

    @contextmanager
    def transaction(self):
        self.transaction_entries += 1
        yield self


class _FakePool:
    def __init__(self) -> None:
        self.connection_value = _FakeConnection()
        self.open_calls: list[bool] = []
        self.closed = False

    def open(self, *, wait: bool) -> None:
        self.open_calls.append(wait)

    @contextmanager
    def connection(self):
        yield self.connection_value

    def close(self) -> None:
        self.closed = True


class _RecordingPoolFactory:
    def __init__(self) -> None:
        self.kwargs: dict[str, object] = {}
        self.pool = _FakePool()

    def __call__(self, **kwargs: object) -> _FakePool:
        self.kwargs = kwargs
        return self.pool


def test_postgres_adapter_uses_bounded_injected_pool_and_transaction() -> None:
    pool_factory = _RecordingPoolFactory()
    config = DatabaseConfig(
        environment=Environment.STAGING,
        url="postgresql://guardian:secret@db.internal/guardian?sslmode=verify-full",
        pool_min_size=1,
        pool_max_size=8,
    )

    database = create_database(config, pool_factory=pool_factory)

    assert isinstance(database, PostgresDatabase)
    assert pool_factory.kwargs == {
        "conninfo": config.url,
        "min_size": 1,
        "max_size": 8,
        "open": False,
    }
    with database.transaction() as connection:
        assert connection is pool_factory.pool.connection_value
    assert pool_factory.pool.open_calls == [True]
    assert pool_factory.pool.connection_value.transaction_entries == 1
    database.close()
    assert pool_factory.pool.closed is True


def test_sqlite_adapter_commits_and_rolls_back_transactions(tmp_path: Path) -> None:
    config = DatabaseConfig(
        environment=Environment.TEST,
        url=f"sqlite:///{tmp_path / 'guardian.db'}",
        pool_min_size=1,
        pool_max_size=1,
    )
    database = create_database(config)
    assert isinstance(database, SQLiteDatabase)

    with database.transaction() as connection:
        connection.execute("CREATE TABLE events(value TEXT NOT NULL)")
        connection.execute("INSERT INTO events(value) VALUES (?)", ("committed",))

    with pytest.raises(RuntimeError, match="rollback"):
        with database.transaction() as connection:
            connection.execute("INSERT INTO events(value) VALUES (?)", ("rolled-back",))
            raise RuntimeError("rollback")

    with sqlite3.connect(tmp_path / "guardian.db") as connection:
        values = [row[0] for row in connection.execute("SELECT value FROM events")]
    assert values == ["committed"]


def test_sqlite_is_rejected_when_database_factory_receives_production_config() -> None:
    config = DatabaseConfig(
        environment=Environment.PRODUCTION,
        url="sqlite:////tmp/guardian.db",
        pool_min_size=1,
        pool_max_size=1,
    )

    with pytest.raises(ValueError, match="PostgreSQL"):
        create_database(config)
