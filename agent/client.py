from __future__ import annotations

import json
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


class GuardianAPIError(RuntimeError):
    pass


class GuardianAPIClient:
    def __init__(self, base_url: str, timeout: float = 10):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def _request(
        self,
        method: str,
        path: str,
        payload: Any | None = None,
        content_type: str = "application/json",
    ) -> Any:
        data: bytes | None
        if payload is None:
            data = None
        elif isinstance(payload, bytes):
            data = payload
        else:
            data = json.dumps(payload).encode("utf-8")
        request = Request(
            f"{self.base_url}{path}",
            data=data,
            method=method,
            headers={"Content-Type": content_type, "Accept": "application/json"},
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

    def pending_commands(self, device_id: str, after_id: int) -> list[dict[str, Any]]:
        return self._request("GET", f"/api/devices/{device_id}/commands?after_id={after_id}")

    def acknowledge_command(self, device_id: str, command_id: int) -> dict[str, Any]:
        return self._request("POST", f"/api/devices/{device_id}/commands/{command_id}/ack")
