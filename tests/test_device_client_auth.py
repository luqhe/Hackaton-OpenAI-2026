import json
from datetime import UTC, datetime, timedelta
from urllib.parse import urlsplit

import pytest

import agent.client as client_module
from agent.client import GuardianAPIClient, GuardianAPIError
from guardian_core.device_protocol import (
    CredentialRecord,
    DeviceCredentialStatus,
    DeviceRequestAuthenticator,
    issue_device_credential,
)


class CredentialRepository:
    def __init__(self, record):
        self.record = record

    def get_credential(self, credential_id):
        return self.record if self.record.credential_id == credential_id else None


class ReplayProtector:
    def consume(self, credential_id, nonce, expires_at):
        return True


class JSONResponse:
    def __init__(self, body=b"[]"):
        self.body = body

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self):
        return self.body


def test_authenticated_client_signs_poll_without_identity_or_secret_in_url(monkeypatch) -> None:
    now = datetime(2026, 8, 19, 18, 0, tzinfo=UTC)
    credential = issue_device_credential("device-1")
    record = CredentialRecord.from_issued(
        credential,
        family_id="family-1",
        child_id="child-1",
        status=DeviceCredentialStatus.ACTIVE,
        expires_at=now + timedelta(days=30),
    )
    captured = {}

    def fake_urlopen(request, timeout):
        captured["request"] = request
        captured["timeout"] = timeout
        return JSONResponse()

    monkeypatch.setattr(client_module, "urlopen", fake_urlopen)
    client = GuardianAPIClient(
        "http://localhost",
        credential=credential,
        clock=lambda: now,
        nonce_factory=lambda: "client-nonce-123456789",
        allow_insecure_localhost=True,
    )

    assert client.pending_device_commands(after_id=7) == []

    request = captured["request"]
    split = urlsplit(request.full_url)
    assert split.path == "/api/agent/commands"
    assert split.query == "after_id=7&wait_seconds=20"
    assert credential.device_id not in request.full_url
    assert credential.private_key not in request.full_url
    assert credential.private_key not in request.get_header("Authorization")
    principal = DeviceRequestAuthenticator(
        CredentialRepository(record), ReplayProtector(), clock=lambda: now
    ).authenticate(
        method=request.method,
        target=f"{split.path}?{split.query}",
        body=request.data or b"",
        headers=request.headers,
    )
    assert principal.device_id == "device-1"


def test_authenticated_methods_require_a_credential() -> None:
    client = GuardianAPIClient("https://guardian.example")

    with pytest.raises(GuardianAPIError, match="device credential is required"):
        client.pending_device_commands()


def test_all_device_methods_use_authenticated_identity_free_routes(monkeypatch) -> None:
    now = datetime(2026, 8, 19, 18, 0, tzinfo=UTC)
    credential = issue_device_credential("device-secret-scope")
    captured = []

    def fake_urlopen(request, timeout):
        captured.append(request)
        if request.full_url.endswith("/credentials/rotate"):
            return JSONResponse(
                b'{"credential_id":"cred-rotated","device_id":"device-secret-scope",'
                b'"expires_at":"2026-11-17T18:00:00Z","protocol_version":"1.0"}'
            )
        return JSONResponse(b"{}")

    monkeypatch.setattr(client_module, "urlopen", fake_urlopen)
    client = GuardianAPIClient(
        "https://guardian.example",
        credential=credential,
        clock=lambda: now,
        nonce_factory=lambda: f"nonce-{len(captured):016d}",
    )

    client.get_device_policy()
    client.create_device_incident({"application": "Browser"})
    client.upload_device_text_evidence("incident-1", "evidence")
    client.upload_device_png_evidence("incident-1", b"png")
    client.record_device_telemetry({"screen_changes": 1, "observed_at": now.isoformat()})
    client.pending_device_commands(after_id=9, wait_seconds=4)
    client.acknowledge_device_command(7, result="FAILED", error_code="UNSUPPORTED_COMMAND")
    client.rotate_device_credential("A" * 43, "rotation-key-123456789")

    paths = [urlsplit(request.full_url).path for request in captured]
    assert paths == [
        "/api/agent/policy",
        "/api/agent/incidents",
        "/api/agent/incidents/incident-1/evidence",
        "/api/agent/incidents/incident-1/evidence",
        "/api/agent/telemetry",
        "/api/agent/commands",
        "/api/agent/commands/7/ack",
        "/api/agent/credentials/rotate",
    ]
    assert "device-secret-scope" not in "\n".join(request.full_url for request in captured)
    assert json.loads(captured[1].data) == {"application": "Browser"}
    assert json.loads(captured[4].data) == {
        "screen_changes": 1,
        "observed_at": now.isoformat(),
    }
    assert urlsplit(captured[5].full_url).query == "after_id=9&wait_seconds=4"
    for request in captured:
        assert request.get_header("Authorization") == f"GuardianDevice {credential.credential_id}"


def test_authenticated_client_requires_tls_except_explicit_local_test_mode() -> None:
    credential = issue_device_credential("device-1")

    with pytest.raises(ValueError, match="HTTPS"):
        GuardianAPIClient("http://guardian.example", credential=credential)
    with pytest.raises(ValueError, match="HTTPS"):
        GuardianAPIClient(
            "http://guardian.example",
            credential=credential,
            allow_insecure_localhost=True,
        )
