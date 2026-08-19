from datetime import UTC, datetime, timedelta

import pytest

from guardian_core.device_protocol import (
    CredentialRecord,
    DeviceAuthError,
    DeviceCredentialStatus,
    DeviceRequestAuthenticator,
    issue_device_credential,
    sign_device_request,
)


class CredentialRepository:
    def __init__(self, record: CredentialRecord):
        self.record = record

    def get_credential(self, credential_id: str) -> CredentialRecord | None:
        return self.record if credential_id == self.record.credential_id else None


class ReplayProtector:
    def __init__(self):
        self.seen: set[tuple[str, str]] = set()
        self.expirations: dict[tuple[str, str], datetime] = {}

    def consume(self, credential_id: str, nonce: str, expires_at: datetime) -> bool:
        key = (credential_id, nonce)
        if key in self.seen:
            return False
        self.seen.add(key)
        self.expirations[key] = expires_at
        return True


def protocol_setup(*, status: DeviceCredentialStatus = DeviceCredentialStatus.ACTIVE, expires_in: int = 3600):
    now = datetime(2026, 8, 19, 17, 0, tzinfo=UTC)
    credential = issue_device_credential("device-1")
    record = CredentialRecord.from_issued(
        credential,
        family_id="family-1",
        child_id="child-1",
        status=status,
        expires_at=now + timedelta(seconds=expires_in),
    )
    replay = ReplayProtector()
    authenticator = DeviceRequestAuthenticator(CredentialRepository(record), replay, clock=lambda: now)
    return now, credential, replay, authenticator


def test_signed_request_authenticates_to_the_bound_device_scope() -> None:
    now, credential, _, authenticator = protocol_setup(expires_in=30 * 86_400)
    body = b'{"screen_changes":1}'
    headers = sign_device_request(
        credential,
        method="POST",
        target="/api/agent/telemetry",
        body=body,
        timestamp=now,
        nonce="fixed-nonce-1234567890",
    )

    principal = authenticator.authenticate(
        method="POST",
        target="/api/agent/telemetry",
        body=body,
        headers=headers,
    )

    assert principal.device_id == "device-1"
    assert principal.family_id == "family-1"
    assert principal.child_id == "child-1"
    assert principal.credential_id == credential.credential_id
    assert credential.private_key not in headers["Authorization"]
    record = authenticator.credentials.get_credential(credential.credential_id)
    assert record is not None
    assert record.public_key == credential.public_key
    assert not hasattr(record, "private_key")


@pytest.mark.parametrize(
    ("mutation", "expected_code"),
    [
        ("body", "content_digest_mismatch"),
        ("method", "invalid_signature"),
        ("target", "invalid_signature"),
        ("signature", "invalid_signature"),
    ],
)
def test_request_tampering_fails_closed(mutation: str, expected_code: str) -> None:
    now, credential, _, authenticator = protocol_setup()
    body = b'{"screen_changes":1}'
    headers = sign_device_request(
        credential,
        method="POST",
        target="/api/agent/telemetry",
        body=body,
        timestamp=now,
        nonce="fixed-nonce-1234567890",
    )
    method = "POST"
    target = "/api/agent/telemetry"
    if mutation == "body":
        body = b'{"screen_changes":2}'
    elif mutation == "method":
        method = "PUT"
    elif mutation == "target":
        target = "/api/agent/commands"
    else:
        headers["X-Guardian-Signature"] = "A" * 86

    with pytest.raises(DeviceAuthError) as error:
        authenticator.authenticate(method=method, target=target, body=body, headers=headers)

    assert error.value.code == expected_code
    assert credential.private_key not in str(error.value)


def test_nonce_is_single_use() -> None:
    now, credential, _, authenticator = protocol_setup()
    headers = sign_device_request(
        credential,
        method="GET",
        target="/api/agent/commands?after_id=0",
        timestamp=now,
        nonce="single-use-nonce-12345",
    )
    request = {
        "method": "GET",
        "target": "/api/agent/commands?after_id=0",
        "body": b"",
        "headers": headers,
    }

    authenticator.authenticate(**request)
    with pytest.raises(DeviceAuthError) as error:
        authenticator.authenticate(**request)

    assert error.value.code == "replay_detected"


@pytest.mark.parametrize("offset", [-121, 121])
def test_request_outside_clock_skew_is_rejected(offset: int) -> None:
    now, credential, _, authenticator = protocol_setup()
    headers = sign_device_request(
        credential,
        method="GET",
        target="/api/agent/commands",
        timestamp=now + timedelta(seconds=offset),
        nonce=f"clock-skew-nonce-{offset}",
    )

    with pytest.raises(DeviceAuthError) as error:
        authenticator.authenticate(method="GET", target="/api/agent/commands", body=b"", headers=headers)

    assert error.value.code == "stale_request"


@pytest.mark.parametrize(
    ("status", "expires_in", "expected_code"),
    [
        (DeviceCredentialStatus.REVOKED, 3600, "credential_revoked"),
        (DeviceCredentialStatus.ACTIVE, -1, "credential_expired"),
    ],
)
def test_inactive_credential_is_rejected(status, expires_in: int, expected_code: str) -> None:
    now, credential, _, authenticator = protocol_setup(status=status, expires_in=expires_in)
    headers = sign_device_request(
        credential,
        method="GET",
        target="/api/agent/commands",
        timestamp=now,
        nonce="inactive-credential-nonce",
    )

    with pytest.raises(DeviceAuthError) as error:
        authenticator.authenticate(method="GET", target="/api/agent/commands", body=b"", headers=headers)

    assert error.value.code == expected_code


def test_unsupported_protocol_version_is_rejected() -> None:
    now, credential, _, authenticator = protocol_setup()
    headers = sign_device_request(
        credential,
        method="GET",
        target="/api/agent/commands",
        timestamp=now,
        nonce="unsupported-version-nonce",
    )
    headers["X-Guardian-Protocol-Version"] = "2.0"

    with pytest.raises(DeviceAuthError) as error:
        authenticator.authenticate(method="GET", target="/api/agent/commands", body=b"", headers=headers)

    assert error.value.code == "unsupported_protocol"


def test_secret_is_redacted_and_cannot_be_put_in_query() -> None:
    now, credential, _, _ = protocol_setup()
    assert credential.private_key not in repr(credential)

    with pytest.raises(ValueError, match="secret material"):
        sign_device_request(
            credential,
            method="GET",
            target=f"/api/agent/commands?token={credential.private_key}",
            timestamp=now,
            nonce="query-secret-nonce-123",
        )


def test_duplicate_query_parameters_have_a_stable_canonical_order() -> None:
    now, credential, _, authenticator = protocol_setup()
    headers = sign_device_request(
        credential,
        method="GET",
        target="/api/agent/commands?b=2&a=1&a=0",
        timestamp=now,
        nonce="duplicate-query-nonce",
    )

    principal = authenticator.authenticate(
        method="GET",
        target="/api/agent/commands?a=0&b=2&a=1",
        body=b"",
        headers=headers,
    )

    assert principal.device_id == "device-1"


def test_encoded_path_separator_is_rejected_as_ambiguous() -> None:
    now, credential, _, _ = protocol_setup()

    with pytest.raises(ValueError, match="encoded path separator"):
        sign_device_request(
            credential,
            method="GET",
            target="/api/agent%2Fcommands",
            timestamp=now,
            nonce="encoded-path-nonce-123",
        )


def test_replay_retention_is_bounded_to_the_request_window() -> None:
    now, credential, replay, authenticator = protocol_setup(expires_in=30 * 86_400)
    headers = sign_device_request(
        credential,
        method="GET",
        target="/api/agent/commands",
        timestamp=now,
        nonce="bounded-replay-nonce-1",
    )

    authenticator.authenticate(method="GET", target="/api/agent/commands", body=b"", headers=headers)

    assert replay.expirations[(credential.credential_id, "bounded-replay-nonce-1")] == (
        now + timedelta(seconds=120)
    )


@pytest.mark.parametrize(
    ("header", "value", "expected_code"),
    [
        ("X-Guardian-Nonce", "short", "malformed_request"),
        ("X-Guardian-Nonce", "nonce-with-control\n", "malformed_request"),
        ("X-Guardian-Signature", "not-base64url!", "malformed_request"),
        ("X-Guardian-Content-SHA256", "0" * 4096, "malformed_request"),
        ("Authorization", "GuardianDevice cred-bad\nvalue", "invalid_credential"),
    ],
)
def test_authentication_headers_have_strict_bounds_and_alphabet(
    header: str, value: str, expected_code: str
) -> None:
    now, credential, _, authenticator = protocol_setup()
    headers = sign_device_request(
        credential,
        method="GET",
        target="/api/agent/commands",
        timestamp=now,
        nonce="bounded-header-nonce-1",
    )
    headers[header] = value

    with pytest.raises(DeviceAuthError) as error:
        authenticator.authenticate(method="GET", target="/api/agent/commands", body=b"", headers=headers)

    assert error.value.code == expected_code
