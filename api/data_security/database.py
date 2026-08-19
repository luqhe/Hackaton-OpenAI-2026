from __future__ import annotations

import sqlite3
import threading
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Protocol
from urllib.parse import unquote

from api.data_security.config import LOCAL_ENVIRONMENTS, POSTGRES_SCHEMES, DatabaseConfig


class PoolConnection(Protocol):
    def transaction(self) -> Any: ...


class ConnectionPool(Protocol):
    def open(self, *, wait: bool) -> None: ...

    def connection(self) -> Any: ...

    def close(self) -> None: ...


PoolFactory = Callable[..., ConnectionPool]


class SQLiteDatabase:
    def __init__(self, config: DatabaseConfig):
        config.validate()
        if config.environment not in LOCAL_ENVIRONMENTS:
            raise ValueError("SQLite is restricted to development and test; use managed PostgreSQL")
        self.path = _sqlite_path(config.url)

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.path, timeout=10)
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

    def close(self) -> None:
        return None


class PostgresDatabase:
    def __init__(self, config: DatabaseConfig, pool_factory: PoolFactory | None = None):
        config.validate()
        if config.scheme not in POSTGRES_SCHEMES:
            raise ValueError("PostgresDatabase requires a PostgreSQL URL")
        factory = pool_factory or _load_psycopg_pool_factory()
        self._pool = factory(
            conninfo=config.url,
            min_size=config.pool_min_size,
            max_size=config.pool_max_size,
            open=False,
        )
        self._open = False
        self._open_lock = threading.Lock()

    def _ensure_open(self) -> None:
        with self._open_lock:
            if not self._open:
                self._pool.open(wait=True)
                self._open = True

    @contextmanager
    def transaction(self) -> Iterator[PoolConnection]:
        self._ensure_open()
        with self._pool.connection() as connection, connection.transaction():
            yield connection

    def close(self) -> None:
        self._pool.close()


def create_database(
    config: DatabaseConfig, *, pool_factory: PoolFactory | None = None
) -> SQLiteDatabase | PostgresDatabase:
    config.validate()
    if config.scheme == "sqlite":
        return SQLiteDatabase(config)
    if config.scheme in POSTGRES_SCHEMES:
        return PostgresDatabase(config, pool_factory=pool_factory)
    raise ValueError("Unsupported database URL")


def _sqlite_path(url: str) -> Path:
    prefix = "sqlite:///"
    if not url.startswith(prefix):
        raise ValueError("SQLite URL must use sqlite:///path")
    raw_path = unquote(url.removeprefix(prefix)).split("?", 1)[0]
    if not raw_path:
        raise ValueError("SQLite database URL must include a path")
    return Path(raw_path)


def _load_psycopg_pool_factory() -> PoolFactory:
    try:
        from psycopg_pool import ConnectionPool
    except ImportError as error:
        raise RuntimeError("Managed PostgreSQL requires the optional 'managed' dependencies") from error
    return ConnectionPool
