from datetime import UTC, datetime, timedelta

from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.stage4_onboarding import create_stage4_onboarding_router
from guardian_core.family_experience import FamilyExperienceService, InMemoryFamilyExperienceAdapter


class MutableClock:
    def __init__(self) -> None:
        self.current = datetime(2026, 8, 19, 12, 0, tzinfo=UTC)

    def __call__(self) -> datetime:
        return self.current

    def advance(self, delta: timedelta) -> None:
        self.current += delta


def make_client(*, approved_blocks: set[str] | None = None) -> TestClient:
    service = FamilyExperienceService(
        adapter=InMemoryFamilyExperienceAdapter(),
        approved_block_categories=approved_blocks or set(),
    )
    app = FastAPI()
    app.include_router(create_stage4_onboarding_router(service))
    return TestClient(app)


def test_signup_creates_one_account_and_family_and_rejects_duplicate_email() -> None:
    with make_client() as client:
        created = client.post(
            "/api/onboarding/families",
            json={"email": " Parent@Example.com ", "family_name": "Família Silva"},
        )

        assert created.status_code == 201
        assert created.json()["family_name"] == "Família Silva"
        assert "email" not in created.json()

        duplicate = client.post(
            "/api/onboarding/families",
            json={"email": "parent@example.com", "family_name": "Outra"},
        )
        assert duplicate.status_code == 409
        assert duplicate.json() == {"detail": "Account already exists"}


def test_signup_validation_returns_an_error_without_creating_partial_state() -> None:
    with make_client() as client:
        invalid = client.post(
            "/api/onboarding/families",
            json={"email": "not-an-email", "family_name": "Família Silva"},
        )
        assert invalid.status_code == 422

        valid = client.post(
            "/api/onboarding/families",
            json={"email": "parent@example.com", "family_name": "Família Silva"},
        )
        assert valid.status_code == 201


def test_child_registration_uses_age_band_without_collecting_exact_birth_date() -> None:
    with make_client() as client:
        family_id = client.post(
            "/api/onboarding/families",
            json={"email": "parent@example.com", "family_name": "Família Silva"},
        ).json()["family_id"]

        child = client.post(
            f"/api/onboarding/families/{family_id}/children",
            json={"display_name": "Bia", "age_band": "6_TO_9"},
        )

        assert child.status_code == 201
        body = child.json()
        assert body["age_band"] == "6_TO_9"
        assert body["language_variant"] == "CHILD"
        assert "birth_date" not in body
        assert {rule["action"] for rule in body["initial_policy"]} == {"ALERT"}

        exact_birth_date = client.post(
            f"/api/onboarding/families/{family_id}/children",
            json={"display_name": "Bia", "age_band": "6_TO_9", "birth_date": "2018-03-10"},
        )
        assert exact_birth_date.status_code == 422


def test_initial_policy_only_blocks_categories_with_an_explicit_release_gate() -> None:
    with make_client(approved_blocks={"DANGEROUS_CONTACT"}) as client:
        family_id = client.post(
            "/api/onboarding/families",
            json={"email": "parent@example.com", "family_name": "Família Silva"},
        ).json()["family_id"]
        child = client.post(
            f"/api/onboarding/families/{family_id}/children",
            json={
                "display_name": "Leo",
                "age_band": "13_TO_17",
                "requested_block_categories": ["ADULT_CONTENT", "DANGEROUS_CONTACT"],
            },
        )

        assert child.status_code == 201
        body = child.json()
        assert body["language_variant"] == "TEEN"
        actions = {rule["category"]: rule["action"] for rule in body["initial_policy"]}
        assert actions["DANGEROUS_CONTACT"] == "BLOCK"
        assert actions["ADULT_CONTENT"] == "ALERT"

        missing_family = client.post(
            "/api/onboarding/families/family-other/children",
            json={"display_name": "Outra", "age_band": "10_TO_12"},
        )
        assert missing_family.status_code == 404


def test_age_bands_have_distinct_but_non_blocking_defaults() -> None:
    with make_client() as client:
        family_id = client.post(
            "/api/onboarding/families",
            json={"email": "parent@example.com", "family_name": "Família Silva"},
        ).json()["family_id"]
        younger = client.post(
            f"/api/onboarding/families/{family_id}/children",
            json={"display_name": "Bia", "age_band": "6_TO_9"},
        ).json()
        teen = client.post(
            f"/api/onboarding/families/{family_id}/children",
            json={"display_name": "Leo", "age_band": "13_TO_17"},
        ).json()

        younger_actions = {rule["category"]: rule["action"] for rule in younger["initial_policy"]}
        teen_actions = {rule["category"]: rule["action"] for rule in teen["initial_policy"]}
        assert younger_actions == {
            "ADULT_CONTENT": "ALERT",
            "HATE_SPEECH": "ALERT",
            "DANGEROUS_CONTACT": "ALERT",
            "OTHER": "ALERT",
        }
        assert teen_actions == {
            "ADULT_CONTENT": "ALLOW",
            "HATE_SPEECH": "ALLOW",
            "DANGEROUS_CONTACT": "ALERT",
            "OTHER": "ALLOW",
        }
        assert "BLOCK" not in teen_actions.values()


def test_privacy_notice_and_consent_are_explicit_and_versioned() -> None:
    with make_client() as client:
        family_id = client.post(
            "/api/onboarding/families",
            json={"email": "parent@example.com", "family_name": "Família Silva"},
        ).json()["family_id"]

        notice = client.get("/api/onboarding/privacy-notice")
        assert notice.status_code == 200
        body = notice.json()
        assert body["version"] == "2026-08-19.1"
        assert "exact_birth_date" in body["not_collected"]
        assert body["retention_days"] == {"technical_health": 30, "incident_evidence": 30}
        assert body["access"] == ["authorized_family_members", "authorized_support_when_requested"]

        stale = client.post(
            f"/api/onboarding/families/{family_id}/privacy-consent",
            json={"notice_version": "2026-01-01.1"},
        )
        assert stale.status_code == 409
        assert stale.json()["detail"] == "Privacy notice version is no longer current"

        accepted = client.post(
            f"/api/onboarding/families/{family_id}/privacy-consent",
            json={"notice_version": body["version"]},
        )
        assert accepted.status_code == 201
        assert accepted.json()["notice_version"] == body["version"]
        assert accepted.json()["family_id"] == family_id


def test_pairing_expires_retries_and_reports_dependency_offline() -> None:
    clock = MutableClock()
    adapter = InMemoryFamilyExperienceAdapter()
    service = FamilyExperienceService(adapter=adapter, now=clock, pairing_ttl=timedelta(minutes=5))
    app = FastAPI()
    app.include_router(create_stage4_onboarding_router(service))

    with TestClient(app) as client:
        family_id = client.post(
            "/api/onboarding/families",
            json={"email": "parent@example.com", "family_name": "Família Silva"},
        ).json()["family_id"]
        child_id = client.post(
            f"/api/onboarding/families/{family_id}/children",
            json={"display_name": "Bia", "age_band": "10_TO_12"},
        ).json()["child_id"]
        issued = client.post(
            f"/api/onboarding/families/{family_id}/children/{child_id}/pairing",
            json={"device_name": "Mac da Bia"},
        )
        assert issued.status_code == 201
        first = issued.json()
        assert first["attempt"] == 1
        assert len(first["code"]) == 8

        clock.advance(timedelta(minutes=6))
        expired = client.post("/api/onboarding/pairing/redeem", json={"code": first["code"]})
        assert expired.status_code == 410
        assert expired.json() == {"detail": "Pairing code expired"}

        malformed = client.post("/api/onboarding/pairing/redeem", json={"code": "!!!!!!!!"})
        assert malformed.status_code == 422

        adapter.set_pairing_available(False)
        offline = client.post(f"/api/onboarding/pairing/{first['pairing_id']}/retry")
        assert offline.status_code == 503
        assert offline.json() == {"detail": "Pairing service temporarily unavailable"}

        adapter.set_pairing_available(True)
        retry = client.post(f"/api/onboarding/pairing/{first['pairing_id']}/retry")
        assert retry.status_code == 201
        assert retry.json()["attempt"] == 2
        assert retry.json()["code"] != first["code"]

        paired = client.post(
            "/api/onboarding/pairing/redeem",
            json={"code": retry.json()["code"]},
        )
        assert paired.status_code == 201
        assert paired.json()["child_id"] == child_id
        assert paired.json()["device_name"] == "Mac da Bia"


def test_protection_requires_recent_heartbeat_and_all_required_permissions() -> None:
    clock = MutableClock()
    service = FamilyExperienceService(
        adapter=InMemoryFamilyExperienceAdapter(),
        now=clock,
        heartbeat_ttl=timedelta(minutes=2),
    )
    app = FastAPI()
    app.include_router(create_stage4_onboarding_router(service))

    with TestClient(app) as client:
        family_id = client.post(
            "/api/onboarding/families",
            json={"email": "parent@example.com", "family_name": "Família Silva"},
        ).json()["family_id"]
        child_id = client.post(
            f"/api/onboarding/families/{family_id}/children",
            json={"display_name": "Bia", "age_band": "10_TO_12"},
        ).json()["child_id"]
        challenge = client.post(
            f"/api/onboarding/families/{family_id}/children/{child_id}/pairing",
            json={"device_name": "Mac da Bia"},
        ).json()
        device = client.post(
            "/api/onboarding/pairing/redeem",
            json={"code": challenge["code"]},
        ).json()
        device_id = device["device_id"]

        pending = client.get(f"/api/onboarding/devices/{device_id}/protection").json()
        assert pending["status"] == "PENDING"
        assert pending["reason"] == "awaiting_first_heartbeat"
        assert set(pending["permissions"].values()) == {"UNKNOWN"}

        healthy_permissions = {
            "SCREEN_RECORDING": "GRANTED",
            "ACCESSIBILITY": "GRANTED",
            "AUTOMATION": "GRANTED",
        }
        heartbeat = client.post(
            f"/api/onboarding/devices/{device_id}/heartbeat",
            json={
                "observed_at": clock().isoformat(),
                "agent_version": "1.0.0",
                "permissions": healthy_permissions,
            },
        )
        assert heartbeat.status_code == 200
        assert heartbeat.json()["status"] == "PROTECTED"

        revoked = client.post(
            f"/api/onboarding/devices/{device_id}/heartbeat",
            json={
                "observed_at": (clock() + timedelta(seconds=1)).isoformat(),
                "agent_version": "1.0.0",
                "permissions": {**healthy_permissions, "SCREEN_RECORDING": "REVOKED"},
            },
        )
        assert revoked.json()["status"] == "DEGRADED"
        assert revoked.json()["reason"] == "permissions_invalid"

        restored_at = clock() + timedelta(seconds=2)
        restored = client.post(
            f"/api/onboarding/devices/{device_id}/heartbeat",
            json={
                "observed_at": restored_at.isoformat(),
                "agent_version": "1.0.0",
                "permissions": healthy_permissions,
            },
        )
        assert restored.json()["status"] == "PROTECTED"

        clock.advance(timedelta(minutes=3))
        stale = client.get(f"/api/onboarding/devices/{device_id}/protection").json()
        assert stale["status"] == "DEGRADED"
        assert stale["reason"] == "heartbeat_stale"

        future = client.post(
            f"/api/onboarding/devices/{device_id}/heartbeat",
            json={
                "observed_at": (clock() + timedelta(days=1)).isoformat(),
                "agent_version": "1.0.0",
                "permissions": healthy_permissions,
            },
        )
        assert future.status_code == 422
        assert future.json() == {"detail": "Heartbeat timestamp is invalid"}
        assert client.get(f"/api/onboarding/devices/{device_id}/protection").json()["status"] == "DEGRADED"
