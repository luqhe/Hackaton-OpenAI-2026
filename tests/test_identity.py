import sqlite3
from dataclasses import FrozenInstanceError

import pytest

from api.storage import GuardianStore
from guardian_core import models
from guardian_core.config import Environment


def test_family_scope_is_an_immutable_tenant_capability() -> None:
    scope = models.FamilyScope(
        account_id="account-a",
        family_id="family-a",
        membership_id="membership-a",
        role=models.MembershipRole.OWNER,
    )

    assert scope.family_id == "family-a"
    with pytest.raises(FrozenInstanceError):
        scope.family_id = "family-b"


def test_child_and_device_carry_their_family_identity() -> None:
    child = models.Child(
        id="child-a",
        family_id="family-a",
        name="Lia",
        created_at="2026-08-19T12:00:00Z",
    )
    device = models.Device(
        id="device-a",
        family_id="family-a",
        child_id=child.id,
        name="MacBook",
        platform="macOS",
        paired_at="2026-08-19T12:00:00Z",
        last_seen_at=None,
        lifecycle_status=models.DeviceLifecycleStatus.ACTIVE,
        protection_status="DEGRADED",
    )

    assert child.family_id == device.family_id
    assert device.lifecycle_status == models.DeviceLifecycleStatus.ACTIVE


def test_account_can_own_multiple_families_and_family_creation_is_atomic(tmp_path) -> None:
    store = GuardianStore(
        tmp_path / "guardian.db",
        tmp_path / "evidence",
        environment=Environment.TEST,
        demo_mode=False,
    )
    store.initialize()
    account = store.create_account(" OWNER@Example.COM ", "valid-password-hash")

    family_a, membership_a = store.create_family_with_owner(account.id, "Família A")
    family_b, membership_b = store.create_family_with_owner(account.id, "Família B")

    assert account.email == "owner@example.com"
    assert {membership_a.account_id, membership_b.account_id} == {account.id}
    assert {membership_a.family_id, membership_b.family_id} == {family_a.id, family_b.id}
    with pytest.raises(KeyError):
        store.create_family_with_owner("missing-account", "Órfã")
    with store.connect() as connection:
        assert connection.execute("SELECT COUNT(*) FROM families WHERE name = 'Órfã'").fetchone()[0] == 0


def test_membership_is_unique_and_last_active_owner_cannot_be_revoked(tmp_path) -> None:
    store = GuardianStore(
        tmp_path / "guardian.db",
        tmp_path / "evidence",
        environment=Environment.TEST,
        demo_mode=False,
    )
    store.initialize()
    first = store.create_account("first@example.com", "hash-a")
    second = store.create_account("second@example.com", "hash-b")
    family, first_owner = store.create_family_with_owner(first.id, "Família")

    with pytest.raises(sqlite3.IntegrityError):
        store.add_membership(first.id, family.id, models.MembershipRole.GUARDIAN)
    with pytest.raises(ValueError, match="last active owner"):
        store.revoke_membership(family.id, first_owner.id)

    second_owner = store.add_membership(second.id, family.id, models.MembershipRole.OWNER)
    revoked = store.revoke_membership(family.id, first_owner.id)

    assert revoked.status == models.MembershipStatus.REVOKED
    assert second_owner.status == models.MembershipStatus.ACTIVE


def test_store_seeds_demo_only_when_explicit_and_is_idempotent(tmp_path) -> None:
    database = tmp_path / "guardian.db"
    store = GuardianStore(
        database,
        tmp_path / "evidence",
        environment=Environment.TEST,
        demo_mode=False,
    )
    store.initialize()

    with sqlite3.connect(database) as connection:
        assert connection.execute("SELECT COUNT(*) FROM families").fetchone()[0] == 0

    demo_store = GuardianStore(
        database,
        tmp_path / "evidence",
        environment=Environment.TEST,
        demo_mode=True,
    )
    demo_store.initialize()
    demo_store.initialize()

    with sqlite3.connect(database) as connection:
        assert connection.execute("SELECT id FROM families").fetchall() == [("family-demo",)]
        assert connection.execute("SELECT family_id FROM children").fetchall() == [("family-demo",)]
        assert connection.execute("SELECT family_id FROM devices").fetchall() == [("family-demo",)]
        assert connection.execute(
            "SELECT auth_enabled, password_hash FROM accounts WHERE id = 'account-demo'"
        ).fetchone() == (0, None)


def test_schema_rejects_cross_family_device_and_incident_links(tmp_path) -> None:
    database = tmp_path / "guardian.db"
    store = GuardianStore(
        database,
        tmp_path / "evidence",
        environment=Environment.TEST,
        demo_mode=False,
    )
    store.initialize()

    with sqlite3.connect(database) as connection:
        connection.execute("PRAGMA foreign_keys = ON")
        now = "2026-08-19T12:00:00Z"
        connection.executemany(
            "INSERT INTO families(id, name, created_at) VALUES (?, ?, ?)",
            [("family-a", "A", now), ("family-b", "B", now)],
        )
        connection.executemany(
            "INSERT INTO children(id, family_id, name, created_at) VALUES (?, ?, ?, ?)",
            [("child-a", "family-a", "A", now), ("child-b", "family-b", "B", now)],
        )
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                """
                INSERT INTO devices(
                    id, family_id, child_id, name, platform, paired_at, lifecycle_status
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                ("device-cross", "family-a", "child-b", "Mac", "macOS", now, "ACTIVE"),
            )

        connection.execute(
            """
            INSERT INTO devices(
                id, family_id, child_id, name, platform, paired_at, lifecycle_status
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            ("device-a", "family-a", "child-a", "Mac", "macOS", now, "ACTIVE"),
        )
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                """
                INSERT INTO incidents(
                    id, family_id, child_id, device_id, application, occurred_at,
                    category, direction, severity, confidence, explanation,
                    evidence_json, policy_action, status, deduplication_key,
                    created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "incident-cross",
                    "family-b",
                    "child-b",
                    "device-a",
                    "Safari",
                    now,
                    "OTHER",
                    "CHILD_AS_TARGET",
                    "HIGH",
                    0.9,
                    "test",
                    "[]",
                    "ALERT",
                    "DETECTED",
                    "dedupe-cross-family",
                    now,
                    now,
                ),
            )


def test_session_cannot_mix_account_and_membership_from_same_family(tmp_path) -> None:
    database = tmp_path / "guardian.db"
    store = GuardianStore(
        database,
        tmp_path / "evidence",
        environment=Environment.TEST,
        demo_mode=False,
    )
    store.initialize()
    account_a = store.create_account("a@example.com", "hash-a")
    account_b = store.create_account("b@example.com", "hash-b")
    family, membership_a = store.create_family_with_owner(account_a.id, "Família")
    membership_b = store.add_membership(account_b.id, family.id, models.MembershipRole.OWNER)

    with sqlite3.connect(database) as connection:
        connection.execute("PRAGMA foreign_keys = ON")
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                """
                INSERT INTO auth_sessions(
                    id, token_hash, csrf_hash, account_id, family_id, membership_id,
                    created_at, expires_at, last_seen_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "session-mixed",
                    "token-hash",
                    "csrf-hash",
                    account_a.id,
                    family.id,
                    membership_b.id,
                    "2026-08-19T12:00:00Z",
                    "2026-08-20T12:00:00Z",
                    "2026-08-19T12:00:00Z",
                ),
            )

    assert membership_a.account_id != membership_b.account_id


def test_version_one_demo_data_migrates_once_into_demo_family(tmp_path) -> None:
    database = tmp_path / "guardian.db"
    with sqlite3.connect(database) as connection:
        connection.executescript(
            """
            CREATE TABLE children (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            CREATE TABLE devices (
                id TEXT PRIMARY KEY,
                child_id TEXT NOT NULL REFERENCES children(id),
                name TEXT NOT NULL,
                platform TEXT NOT NULL,
                paired_at TEXT NOT NULL,
                last_seen_at TEXT,
                protection_status TEXT NOT NULL
            );
            INSERT INTO children VALUES ('child-demo', 'Lucas', '2026-08-19T12:00:00Z');
            INSERT INTO devices VALUES (
                'device-demo', 'child-demo', 'MacBook', 'macOS',
                '2026-08-19T12:00:00Z', NULL, 'PROTECTED'
            );
            PRAGMA user_version = 1;
            """
        )

    store = GuardianStore(
        database,
        tmp_path / "evidence",
        environment=Environment.TEST,
        demo_mode=True,
    )
    store.initialize()
    store.initialize()

    with sqlite3.connect(database) as connection:
        assert connection.execute("SELECT family_id, id FROM children ORDER BY id").fetchall() == [
            ("family-demo", "child-demo")
        ]
        assert connection.execute("SELECT family_id, child_id, id FROM devices ORDER BY id").fetchall() == [
            ("family-demo", "child-demo", "device-demo")
        ]


def test_production_rejects_demo_residue(tmp_path) -> None:
    database = tmp_path / "guardian.db"
    demo_store = GuardianStore(
        database,
        tmp_path / "evidence",
        environment=Environment.TEST,
        demo_mode=True,
    )
    demo_store.initialize()

    production_store = GuardianStore(
        database,
        tmp_path / "evidence",
        environment=Environment.PRODUCTION,
        demo_mode=False,
    )
    with pytest.raises(RuntimeError, match="demo data"):
        production_store.initialize()
