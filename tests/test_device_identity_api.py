import json
from datetime import UTC, datetime, timedelta

from fastapi import Request
from fastapi.testclient import TestClient

from api.main import create_app
from guardian_core.config import Environment, GuardianSettings
from guardian_core.device_protocol import (
    IssuedDeviceCredential,
    generate_device_key_pair,
    sign_device_request,
)
from guardian_core.identity import FamilyScope, MembershipRole


def settings(tmp_path) -> GuardianSettings:
    return GuardianSettings(
        environment=Environment.TEST,
        database_path=tmp_path / "guardian.db",
        evidence_directory=tmp_path / "evidence",
        api_url="http://localhost",
        log_level="INFO",
        automatic_blocking_enabled=False,
        real_enforcement_enabled=False,
        release_gate_approved=False,
        demo_mode=False,
    )


def scope_resolver(request: Request) -> FamilyScope:
    family_id = request.headers["x-test-family"]
    return FamilyScope(
        account_id=f"account-{family_id}",
        family_id=family_id,
        membership_id=f"membership-{family_id}",
        role=MembershipRole.OWNER,
    )


def seed_family(app, family_id: str, child_id: str) -> None:
    now = datetime.now(UTC).isoformat()
    with app.state.store.connect() as connection:
        connection.execute(
            "INSERT INTO families(id, name, created_at) VALUES (?, ?, ?)",
            (family_id, family_id, now),
        )
        connection.execute(
            "INSERT INTO children(id, family_id, name, created_at) VALUES (?, ?, ?, ?)",
            (child_id, family_id, child_id, now),
        )


def pair(client: TestClient, family_id: str, child_id: str, installation_id: str | None = None):
    challenge = client.post(
        "/api/pairing/challenges",
        headers={"X-Test-Family": family_id},
        json={"child_id": child_id},
    )
    assert challenge.status_code == 201
    key_pair = generate_device_key_pair(installation_id)
    confirmed = client.post(
        "/api/device/pair",
        json={
            "challenge_id": challenge.json()["challenge_id"],
            "code": challenge.json()["code"],
            "device_name": "MacBook",
            "platform": "macOS",
            "installation_id": key_pair.installation_id,
            "public_key": key_pair.public_key,
        },
    )
    assert confirmed.status_code == 201
    metadata = confirmed.json()
    credential = IssuedDeviceCredential(
        credential_id=metadata["credential_id"],
        device_id=metadata["device_id"],
        public_key=key_pair.public_key,
        private_key=key_pair.private_key,
        installation_id=key_pair.installation_id,
    )
    return challenge.json(), credential


def signed_request(client, credential, method, target, now, payload=None):
    body = b"" if payload is None else json.dumps(payload, separators=(",", ":")).encode()
    headers = sign_device_request(
        credential,
        method=method,
        target=target,
        body=body,
        timestamp=now,
        nonce=f"nonce-{now.timestamp():.0f}-{len(target)}",
    )
    if payload is not None:
        headers["Content-Type"] = "application/json"
    return client.request(method, target, content=body or None, headers=headers)


def incident_payload() -> dict:
    return {
        "application": "Guardian Demo Chat",
        "occurred_at": "2026-08-19T18:00:00Z",
        "assessment": {
            "risk": "HIGH",
            "category": "DANGEROUS_CONTACT",
            "direction": "CHILD_AS_TARGET",
            "confidence": 0.94,
            "evidence": ["progressive request"],
            "explanation": "Progressive personal-information requests.",
        },
        "decision": {"action": "BLOCK", "matched_rule": None, "reason": "Policy matched"},
        "deduplication_key": "authenticated-incident-1",
    }


def test_pairing_is_short_lived_single_use_and_authenticates_device_scope(tmp_path) -> None:
    now = datetime(2026, 8, 19, 18, 0, tzinfo=UTC)
    app = create_app(
        settings=settings(tmp_path),
        family_scope_resolver=scope_resolver,
        device_clock=lambda: now,
        pairing_pepper=b"pairing-test-pepper-with-at-least-32-bytes",
    )
    with TestClient(app) as client:
        seed_family(app, "family-a", "child-a")
        challenge, credential = pair(client, "family-a", "child-a")

        assert len(challenge["code"].replace("-", "")) == 8
        assert datetime.fromisoformat(challenge["expires_at"]) == now + timedelta(minutes=10)
        replay = client.post(
            "/api/device/pair",
            json={
                "challenge_id": challenge["challenge_id"],
                "code": challenge["code"],
                "device_name": "Replay",
                "platform": "macOS",
                "installation_id": generate_device_key_pair().installation_id,
                "public_key": generate_device_key_pair().public_key,
            },
        )
        assert replay.status_code == 410

        response = signed_request(client, credential, "GET", "/api/agent/policy", now)
        assert response.status_code == 200
        assert response.json() == []


def test_pairing_locks_after_five_wrong_codes(tmp_path) -> None:
    now = datetime(2026, 8, 19, 18, 0, tzinfo=UTC)
    app = create_app(
        settings=settings(tmp_path),
        family_scope_resolver=scope_resolver,
        device_clock=lambda: now,
        pairing_pepper=b"pairing-test-pepper-with-at-least-32-bytes",
    )
    with TestClient(app) as client:
        seed_family(app, "family-a", "child-a")
        challenge = client.post(
            "/api/pairing/challenges",
            headers={"X-Test-Family": "family-a"},
            json={"child_id": "child-a"},
        ).json()
        key_pair = generate_device_key_pair()
        payload = {
            "challenge_id": challenge["challenge_id"],
            "code": "2222-2222",
            "device_name": "MacBook",
            "platform": "macOS",
            "installation_id": key_pair.installation_id,
            "public_key": key_pair.public_key,
        }
        for _ in range(5):
            assert client.post("/api/device/pair", json=payload).status_code == 410
        payload["code"] = challenge["code"]

        assert client.post("/api/device/pair", json=payload).status_code == 410
        payload["code"] = "ÅÅÅÅ-ÅÅÅÅ"
        assert client.post("/api/device/pair", json=payload).status_code == 422


def test_authenticated_incident_ignores_no_client_identity_and_rejects_identity_fields(tmp_path) -> None:
    now = datetime(2026, 8, 19, 18, 0, tzinfo=UTC)
    app = create_app(
        settings=settings(tmp_path),
        family_scope_resolver=scope_resolver,
        device_clock=lambda: now,
        pairing_pepper=b"pairing-test-pepper-with-at-least-32-bytes",
    )
    with TestClient(app) as client:
        seed_family(app, "family-a", "child-a")
        _, credential = pair(client, "family-a", "child-a")
        created = signed_request(client, credential, "POST", "/api/agent/incidents", now, incident_payload())
        assert created.status_code == 201
        assert created.json()["family_id"] == "family-a"
        assert created.json()["child_id"] == "child-a"
        assert created.json()["device_id"] == credential.device_id

        forged = incident_payload() | {"child_id": "child-b", "device_id": "device-b"}
        rejected = signed_request(
            client,
            credential,
            "POST",
            "/api/agent/incidents",
            now + timedelta(seconds=1),
            forged,
        )
        assert rejected.status_code == 422


def test_rotation_grace_repair_revokes_old_identity_and_parent_revocation_fails_closed(tmp_path) -> None:
    clock = [datetime(2026, 8, 19, 18, 0, tzinfo=UTC)]
    app = create_app(
        settings=settings(tmp_path),
        family_scope_resolver=scope_resolver,
        device_clock=lambda: clock[0],
        pairing_pepper=b"pairing-test-pepper-with-at-least-32-bytes",
    )
    with TestClient(app) as client:
        seed_family(app, "family-a", "child-a")
        seed_family(app, "family-b", "child-b")
        _, old_credential = pair(client, "family-a", "child-a", "install-stable-123456789")
        _, new_credential = pair(client, "family-b", "child-b", "install-stable-123456789")

        assert signed_request(client, old_credential, "GET", "/api/agent/policy", clock[0]).status_code == 401
        assert signed_request(client, new_credential, "GET", "/api/agent/policy", clock[0]).status_code == 200
        revoked = client.post(
            f"/api/devices/{new_credential.device_id}/credentials/revoke",
            headers={"X-Test-Family": "family-b"},
        )
        assert revoked.status_code == 204
        assert (
            signed_request(
                client,
                new_credential,
                "GET",
                "/api/agent/policy",
                clock[0] + timedelta(seconds=1),
            ).status_code
            == 401
        )


def test_rotation_has_grace_and_idempotency_key_cannot_change_public_key(tmp_path) -> None:
    clock = [datetime(2026, 8, 19, 18, 0, tzinfo=UTC)]
    app = create_app(
        settings=settings(tmp_path),
        family_scope_resolver=scope_resolver,
        device_clock=lambda: clock[0],
        pairing_pepper=b"pairing-test-pepper-with-at-least-32-bytes",
    )
    with TestClient(app) as client:
        seed_family(app, "family-a", "child-a")
        _, old = pair(client, "family-a", "child-a")
        rotated_keys = generate_device_key_pair(old.installation_id)
        rotation_payload = {
            "public_key": rotated_keys.public_key,
            "idempotency_key": "rotation-key-123456789",
        }
        rotated = signed_request(
            client,
            old,
            "POST",
            "/api/agent/credentials/rotate",
            clock[0],
            rotation_payload,
        )
        assert rotated.status_code == 200
        metadata = rotated.json()
        new = IssuedDeviceCredential(
            credential_id=metadata["credential_id"],
            device_id=metadata["device_id"],
            public_key=rotated_keys.public_key,
            private_key=rotated_keys.private_key,
            installation_id=old.installation_id,
        )
        conflicting_keys = generate_device_key_pair(old.installation_id)
        conflict = signed_request(
            client,
            old,
            "POST",
            "/api/agent/credentials/rotate",
            clock[0] + timedelta(seconds=1),
            {
                "public_key": conflicting_keys.public_key,
                "idempotency_key": "rotation-key-123456789",
            },
        )
        assert conflict.status_code == 409

        clock[0] += timedelta(minutes=4, seconds=59)
        assert signed_request(client, old, "GET", "/api/agent/policy", clock[0]).status_code == 200
        clock[0] += timedelta(seconds=2)
        assert signed_request(client, old, "GET", "/api/agent/policy", clock[0]).status_code == 401
        assert signed_request(client, new, "GET", "/api/agent/policy", clock[0]).status_code == 200


def test_commands_are_versioned_expiring_idempotent_and_device_bound(tmp_path) -> None:
    now = datetime(2026, 8, 19, 18, 0, tzinfo=UTC)
    app = create_app(
        settings=settings(tmp_path),
        family_scope_resolver=scope_resolver,
        device_clock=lambda: now,
        pairing_pepper=b"pairing-test-pepper-with-at-least-32-bytes",
    )
    with TestClient(app) as client:
        seed_family(app, "family-a", "child-a")
        _, credential = pair(client, "family-a", "child-a")
        incident = signed_request(
            client, credential, "POST", "/api/agent/incidents", now, incident_payload()
        ).json()
        assert client.post(f"/api/incidents/{incident['id']}/unlock").status_code == 200

        polled = signed_request(
            client,
            credential,
            "GET",
            "/api/agent/commands?after_id=0&wait_seconds=0",
            now + timedelta(seconds=1),
        )
        assert polled.status_code == 200
        command = polled.json()[0]
        assert command["protocol_version"] == "1.0"
        assert command["type"] == "UNLOCK_APPLICATION"
        assert command["idempotency_key"] == f"unlock:{incident['id']}"
        assert datetime.fromisoformat(command["expires_at"]) > now

        ack_target = f"/api/agent/commands/{command['id']}/ack"
        ack = signed_request(
            client,
            credential,
            "POST",
            ack_target,
            now + timedelta(seconds=2),
            {"result": "EXECUTED"},
        )
        assert ack.status_code == 200
        assert ack.json()["status"] == "ACKNOWLEDGED"
        repeated = signed_request(
            client,
            credential,
            "POST",
            ack_target,
            now + timedelta(seconds=3),
            {"result": "EXECUTED"},
        )
        assert repeated.status_code == 200
        assert repeated.json()["status"] == "ACKNOWLEDGED"
