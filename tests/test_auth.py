from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from api import auth
from api.main import create_app
from guardian_core.config import GuardianSettings
from guardian_core.models import DevicePairRequest


def settings_for(tmp_path: Path, *, demo_mode: bool = False) -> GuardianSettings:
    return GuardianSettings.from_env(
        {
            "GUARDIAN_ENVIRONMENT": "test",
            "GUARDIAN_DB_PATH": str(tmp_path / "guardian.db"),
            "GUARDIAN_EVIDENCE_DIR": str(tmp_path / "evidence"),
            "GUARDIAN_API_URL": "http://testserver",
            "GUARDIAN_AUTOMATIC_BLOCKING_ENABLED": "false",
            "GUARDIAN_REAL_ENFORCEMENT_ENABLED": "false",
            "GUARDIAN_RELEASE_GATE_APPROVED": "false",
            "GUARDIAN_DEMO_MODE": "true" if demo_mode else "false",
        }
    )


@pytest.mark.parametrize(
    "path",
    [
        "/api/devices/missing",
        "/api/children/missing/policy",
        "/api/incidents?child_id=missing",
        "/api/incidents/missing",
        "/api/evidence/missing",
        "/api/devices/missing/commands",
        "/api/daily-report?child_id=missing",
    ],
)
def test_family_routes_reject_anonymous_requests(tmp_path, path) -> None:
    app = create_app(settings=settings_for(tmp_path))

    with TestClient(app) as client:
        response = client.get(path)

    assert response.status_code == 401
    assert response.json() == {"detail": "Authentication required"}


def create_family_login(client: TestClient, email: str = "owner@example.com") -> dict[str, str]:
    store = client.app.state.store
    account = store.create_account(email, auth.hash_password("correct horse battery staple"))
    family, membership = store.create_family_with_owner(account.id, "Família Teste")
    return {
        "account_id": account.id,
        "family_id": family.id,
        "membership_id": membership.id,
        "email": email,
    }


def test_login_uses_an_opaque_secure_session_and_resolves_family_scope(tmp_path) -> None:
    app = create_app(settings=settings_for(tmp_path))
    with TestClient(app) as client:
        identity = create_family_login(client)

        response = client.post(
            "/api/auth/login",
            json={
                "email": identity["email"],
                "password": "correct horse battery staple",
                "family_id": identity["family_id"],
            },
        )
        session = client.get("/api/auth/session")

    assert response.status_code == 200
    assert "guardian_session=" in response.headers["set-cookie"]
    assert "HttpOnly" in response.headers["set-cookie"]
    assert "SameSite=strict" in response.headers["set-cookie"]
    assert session.json() == {
        "account_id": identity["account_id"],
        "family_id": identity["family_id"],
        "membership_id": identity["membership_id"],
        "role": "OWNER",
    }


def test_login_does_not_reveal_whether_an_account_exists(tmp_path) -> None:
    app = create_app(settings=settings_for(tmp_path))
    with TestClient(app) as client:
        identity = create_family_login(client)
        wrong_password = client.post(
            "/api/auth/login",
            json={"email": identity["email"], "password": "incorrect password"},
        )
        missing_account = client.post(
            "/api/auth/login",
            json={"email": "missing@example.com", "password": "incorrect password"},
        )

    assert wrong_password.status_code == missing_account.status_code == 401
    assert wrong_password.json() == missing_account.json() == {"detail": "Invalid credentials"}


def login_client(client: TestClient, identity: dict[str, str]) -> None:
    response = client.post(
        "/api/auth/login",
        json={
            "email": identity["email"],
            "password": "correct horse battery staple",
            "family_id": identity["family_id"],
        },
    )
    assert response.status_code == 200


def csrf_headers(client: TestClient) -> dict[str, str]:
    return {"X-CSRF-Token": client.cookies["guardian_csrf"]}


def test_mutations_require_csrf_and_logout_revokes_immediately(tmp_path) -> None:
    app = create_app(settings=settings_for(tmp_path))
    with TestClient(app) as client:
        identity = create_family_login(client)
        login_client(client, identity)

        missing_csrf = client.post("/api/auth/logout")
        logged_out = client.post("/api/auth/logout", headers=csrf_headers(client))
        after_logout = client.get("/api/auth/session")

    assert missing_csrf.status_code == 403
    assert logged_out.status_code == 204
    assert after_logout.status_code == 401


def test_logout_all_and_membership_revocation_invalidate_other_sessions(tmp_path) -> None:
    app = create_app(settings=settings_for(tmp_path))
    with TestClient(app) as client:
        identity = create_family_login(client)
        login_client(client, identity)
        first_token = client.cookies["guardian_session"]
        client.cookies.clear()
        login_client(client, identity)

        global_logout = client.post("/api/auth/logout-all", headers=csrf_headers(client))
        assert global_logout.status_code == 204
        client.cookies.set("guardian_session", first_token)
        assert client.get("/api/auth/session").status_code == 401

        client.cookies.clear()
        login_client(client, identity)
        store = client.app.state.store
        replacement = store.create_account(
            "replacement@example.com",
            auth.hash_password("replacement secure password"),
        )
        store.add_membership(replacement.id, identity["family_id"], auth.MembershipRole.OWNER)
        store.revoke_membership(identity["family_id"], identity["membership_id"])
        assert client.get("/api/auth/session").status_code == 401


def test_login_is_rate_limited_after_repeated_failures(tmp_path) -> None:
    app = create_app(settings=settings_for(tmp_path))
    with TestClient(app) as client:
        identity = create_family_login(client)
        for _ in range(5):
            response = client.post(
                "/api/auth/login",
                json={"email": identity["email"], "password": "incorrect password"},
            )
            assert response.status_code == 401

        limited = client.post(
            "/api/auth/login",
            json={"email": identity["email"], "password": "incorrect password"},
        )

    assert limited.status_code == 429


def test_password_recovery_is_generic_one_time_and_revokes_sessions(tmp_path) -> None:
    delivered: list[tuple[str, str]] = []
    app = create_app(
        settings=settings_for(tmp_path),
        password_reset_notifier=lambda email, token: delivered.append((email, token)),
    )
    with TestClient(app) as client:
        identity = create_family_login(client)
        login_client(client, identity)

        known = client.post("/api/auth/recovery", json={"email": identity["email"]})
        missing = client.post("/api/auth/recovery", json={"email": "missing@example.com"})
        assert known.status_code == missing.status_code == 202
        assert known.json() == missing.json()
        assert len(delivered) == 1

        reset = client.post(
            "/api/auth/recovery/complete",
            json={
                "token": delivered[0][1],
                "new_password": "a different secure password",
            },
        )
        reused = client.post(
            "/api/auth/recovery/complete",
            json={
                "token": delivered[0][1],
                "new_password": "another different password",
            },
        )
        old_session = client.get("/api/auth/session")
        new_login = client.post(
            "/api/auth/login",
            json={"email": identity["email"], "password": "a different secure password"},
        )

    assert reset.status_code == 204
    assert reused.status_code == 400
    assert old_session.status_code == 401
    assert new_login.status_code == 200


def test_foreign_device_is_indistinguishable_from_missing_device(tmp_path) -> None:
    app = create_app(settings=settings_for(tmp_path))
    with TestClient(app) as client:
        family_a = create_family_login(client, "a@example.com")
        family_b = create_family_login(client, "b@example.com")
        store = client.app.state.store
        child_b = store.create_child(family_b["family_id"], "Bia")
        device_b = store.pair_device(
            family_b["family_id"],
            DevicePairRequest(
                child_id=child_b.id,
                device_name="Mac B",
                platform="macOS",
            ),
        )
        login_client(client, family_a)

        foreign = client.get(f"/api/devices/{device_b.id}")
        missing = client.get("/api/devices/device-missing")

    assert foreign.status_code == missing.status_code == 404
    assert foreign.json() == missing.json()


def incident_for(child_id: str, device_id: str, key: str) -> dict:
    return {
        "child_id": child_id,
        "device_id": device_id,
        "application": "Safari",
        "occurred_at": datetime.now(UTC).isoformat(),
        "assessment": {
            "risk": "HIGH",
            "category": "DANGEROUS_CONTACT",
            "direction": "CHILD_AS_TARGET",
            "confidence": 0.94,
            "evidence": ["request"],
            "explanation": "Personal information requested.",
        },
        "decision": {"action": "BLOCK", "matched_rule": None, "reason": "Family policy"},
        "deduplication_key": key,
    }


def test_cross_tenant_matrix_matches_missing_for_every_family_resource(tmp_path) -> None:
    app = create_app(settings=settings_for(tmp_path))
    with TestClient(app) as client:
        family_a = create_family_login(client, "matrix-a@example.com")
        family_b = create_family_login(client, "matrix-b@example.com")
        store = client.app.state.store
        child_b = store.create_child(family_b["family_id"], "Bia")
        device_b = store.pair_device(
            family_b["family_id"],
            DevicePairRequest(child_id=child_b.id, device_name="Mac B", platform="macOS"),
        )
        login_client(client, family_b)
        created = client.post(
            "/api/incidents",
            json=incident_for(child_b.id, device_b.id, "matrix-incident-b"),
            headers=csrf_headers(client),
        )
        assert created.status_code == 201
        incident_b = created.json()
        evidence = client.post(
            f"/api/incidents/{incident_b['id']}/evidence",
            content=b"minimal evidence",
            headers={**csrf_headers(client), "Content-Type": "text/plain"},
        ).json()
        client.post(
            f"/api/incidents/{incident_b['id']}/unlock",
            headers=csrf_headers(client),
        )
        command_b = client.get(f"/api/devices/{device_b.id}/commands").json()[0]

        login_client(client, family_a)
        csrf = csrf_headers(client)
        policy = [
            {
                "category": "DANGEROUS_CONTACT",
                "action": "ALERT",
                "minimum_risk": "HIGH",
                "minimum_confidence": 0.75,
            }
        ]
        cases = [
            ("get", f"/api/devices/{device_b.id}", {}, "/api/devices/device-missing", {}),
            ("get", f"/api/children/{child_b.id}/policy", {}, "/api/children/child-missing/policy", {}),
            (
                "put",
                f"/api/children/{child_b.id}/policy",
                {"json": policy, "headers": csrf},
                "/api/children/child-missing/policy",
                {"json": policy, "headers": csrf},
            ),
            (
                "post",
                "/api/devices/pair",
                {"json": {"child_id": child_b.id, "device_name": "X", "platform": "macOS"}, "headers": csrf},
                "/api/devices/pair",
                {
                    "json": {"child_id": "child-missing", "device_name": "X", "platform": "macOS"},
                    "headers": csrf,
                },
            ),
            (
                "post",
                "/api/incidents",
                {"json": incident_for(child_b.id, device_b.id, "foreign-create"), "headers": csrf},
                "/api/incidents",
                {"json": incident_for("child-missing", "device-missing", "missing-create"), "headers": csrf},
            ),
            ("get", f"/api/incidents?child_id={child_b.id}", {}, "/api/incidents?child_id=child-missing", {}),
            ("get", f"/api/incidents/{incident_b['id']}", {}, "/api/incidents/inc-missing", {}),
            (
                "post",
                f"/api/incidents/{incident_b['id']}/request-unlock",
                {"json": {"explanation": "Contexto válido"}, "headers": csrf},
                "/api/incidents/inc-missing/request-unlock",
                {"json": {"explanation": "Contexto válido"}, "headers": csrf},
            ),
            (
                "post",
                f"/api/incidents/{incident_b['id']}/unlock",
                {"headers": csrf},
                "/api/incidents/inc-missing/unlock",
                {"headers": csrf},
            ),
            (
                "post",
                f"/api/incidents/{incident_b['id']}/keep-blocked",
                {"headers": csrf},
                "/api/incidents/inc-missing/keep-blocked",
                {"headers": csrf},
            ),
            (
                "post",
                f"/api/incidents/{incident_b['id']}/evidence",
                {"content": b"x", "headers": {**csrf, "Content-Type": "text/plain"}},
                "/api/incidents/inc-missing/evidence",
                {"content": b"x", "headers": {**csrf, "Content-Type": "text/plain"}},
            ),
            ("get", evidence["url"], {}, "/api/evidence/ev-missing", {}),
            ("get", f"/api/devices/{device_b.id}/commands", {}, "/api/devices/device-missing/commands", {}),
            (
                "post",
                f"/api/devices/{device_b.id}/commands/{command_b['id']}/ack",
                {"headers": csrf},
                f"/api/devices/{device_b.id}/commands/999999/ack",
                {"headers": csrf},
            ),
            (
                "post",
                f"/api/devices/{device_b.id}/telemetry",
                {"json": {"child_id": child_b.id}, "headers": csrf},
                "/api/devices/device-missing/telemetry",
                {"json": {"child_id": "child-missing"}, "headers": csrf},
            ),
            (
                "get",
                f"/api/daily-report?child_id={child_b.id}",
                {},
                "/api/daily-report?child_id=child-missing",
                {},
            ),
        ]

        for method, foreign_path, foreign_kwargs, missing_path, missing_kwargs in cases:
            foreign = client.request(method, foreign_path, **foreign_kwargs)
            missing = client.request(method, missing_path, **missing_kwargs)
            assert (
                (foreign.status_code, foreign.json())
                == (
                    missing.status_code,
                    missing.json(),
                )
                == (404, {"detail": "Resource not found"})
            )
