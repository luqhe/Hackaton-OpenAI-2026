from __future__ import annotations

import hashlib
import ipaddress
import json
import secrets
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

from guardian_core.device_protocol import IssuedDeviceCredential, sign_device_request


class GuardianAPIError(RuntimeError):
    pass


class GuardianAPIClient:
    def __init__(
        self,
        base_url: str,
        timeout: float = 10,
        *,
        credential: IssuedDeviceCredential | None = None,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
        nonce_factory: Callable[[], str] = lambda: secrets.token_urlsafe(18),
        allow_insecure_localhost: bool = False,
    ):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.credential = credential
        self.clock = clock
        self.nonce_factory = nonce_factory
        self.allow_insecure_localhost = allow_insecure_localhost
        self._parsed_base_url = urlsplit(self.base_url)
        if credential is not None:
            self._require_secure_transport()

    @property
    def command_scope(self) -> str:
        if self.credential is None:
            raise GuardianAPIError("device credential is required for command scope")
        value = f"{self.base_url}\0{self.credential.device_id}".encode()
        return hashlib.sha256(value).hexdigest()

    def _require_secure_transport(self) -> None:
        if self._parsed_base_url.scheme != "https":
            hostname = self._parsed_base_url.hostname
            loopback = hostname == "localhost"
            if hostname and not loopback:
                try:
                    loopback = ipaddress.ip_address(hostname).is_loopback
                except ValueError:
                    loopback = False
            if self._parsed_base_url.scheme != "http" or not self.allow_insecure_localhost or not loopback:
                raise ValueError("authenticated device requests require HTTPS except on loopback")

    def _request(
        self,
        method: str,
        path: str,
        payload: Any | None = None,
        content_type: str = "application/json",
        authenticated: bool = False,
        secure_transport: bool = False,
    ) -> Any:
        if authenticated or secure_transport:
            self._require_secure_transport()
        data: bytes | None
        if payload is None:
            data = None
        elif isinstance(payload, bytes):
            data = payload
        else:
            data = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        headers = {"Content-Type": content_type, "Accept": "application/json"}
        if authenticated:
            if self.credential is None:
                raise GuardianAPIError("device credential is required for authenticated request")
            headers.update(
                sign_device_request(
                    self.credential,
                    method=method,
                    target=path,
                    body=data or b"",
                    timestamp=self.clock(),
                    nonce=self.nonce_factory(),
                )
            )
        request = Request(
            f"{self.base_url}{path}",
            data=data,
            method=method,
            headers=headers,
        )
        try:
            with urlopen(request, timeout=self.timeout) as response:
                body = response.read()
                return json.loads(body) if body else None
        except HTTPError as error:
            detail = error.read().decode("utf-8", errors="replace")
            raise GuardianAPIError(f"Guardian API returned {error.code}: {detail}") from error
        except URLError as error:
            raise GuardianAPIError(f"Guardian API is unavailable: {error.reason}") from error

    def get_policy(self, child_id: str) -> list[dict[str, Any]]:
        return self._request("GET", f"/api/children/{child_id}/policy")

    def create_incident(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self._request("POST", "/api/incidents", payload)

    def upload_text_evidence(self, incident_id: str, content: str) -> dict[str, str]:
        return self._request(
            "POST",
            f"/api/incidents/{incident_id}/evidence",
            content.encode("utf-8"),
            content_type="text/plain",
        )

    def upload_png_evidence(self, incident_id: str, content: bytes) -> dict[str, str]:
        return self._request(
            "POST",
            f"/api/incidents/{incident_id}/evidence",
            content,
            content_type="image/png",
        )

    def record_telemetry(self, device_id: str, payload: dict[str, Any]) -> None:
        self._request("POST", f"/api/devices/{device_id}/telemetry", payload)

    def record_heartbeat(self, device_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        return self._request("POST", f"/api/devices/{device_id}/heartbeat", payload)

    def pending_commands(self, device_id: str, after_id: int) -> list[dict[str, Any]]:
        return self._request("GET", f"/api/devices/{device_id}/commands?after_id={after_id}")

    def acknowledge_command(self, device_id: str, command_id: int) -> dict[str, Any]:
        return self._request("POST", f"/api/devices/{device_id}/commands/{command_id}/ack")

    def pending_device_commands(self, after_id: int = 0, wait_seconds: float = 20) -> list[dict[str, Any]]:
        target = f"/api/agent/commands?after_id={after_id}&wait_seconds={wait_seconds:g}"
        return self._request("GET", target, authenticated=True)

    def complete_device_pairing(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self._request(
            "POST",
            "/api/device/pair",
            payload,
            secure_transport=True,
        )

    def get_device_policy(self) -> list[dict[str, Any]]:
        return self._request("GET", "/api/agent/policy", authenticated=True)

    def create_device_incident(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self._request("POST", "/api/agent/incidents", payload, authenticated=True)

    def upload_device_text_evidence(self, incident_id: str, content: str) -> dict[str, str]:
        return self._request(
            "POST",
            f"/api/agent/incidents/{incident_id}/evidence",
            content.encode("utf-8"),
            content_type="text/plain",
            authenticated=True,
        )

    def upload_device_png_evidence(self, incident_id: str, content: bytes) -> dict[str, str]:
        return self._request(
            "POST",
            f"/api/agent/incidents/{incident_id}/evidence",
            content,
            content_type="image/png",
            authenticated=True,
        )

    def record_device_heartbeat(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self._request("POST", "/api/agent/heartbeat", payload, authenticated=True)

    def record_device_telemetry(self, payload: dict[str, Any]) -> None:
        self._request("POST", "/api/agent/telemetry", payload, authenticated=True)

    def acknowledge_device_command(
        self,
        command_id: int,
        *,
        result: str,
        error_code: str | None = None,
    ) -> dict[str, Any]:
        payload = {"result": result}
        if error_code is not None:
            payload["error_code"] = error_code
        return self._request(
            "POST",
            f"/api/agent/commands/{command_id}/ack",
            payload,
            authenticated=True,
        )

    def rotate_device_credential(self, public_key: str, idempotency_key: str) -> dict[str, Any]:
        return self._request(
            "POST",
            "/api/agent/credentials/rotate",
            {"public_key": public_key, "idempotency_key": idempotency_key},
            authenticated=True,
        )
