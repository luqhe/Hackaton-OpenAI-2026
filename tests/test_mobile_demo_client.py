from __future__ import annotations

from urllib.request import Request

import agent.client as client_module
from agent.client import GuardianAPIClient


class FakeResponse:
    def __init__(self, payload: bytes = b"[]") -> None:
        self.payload = payload

    def __enter__(self) -> FakeResponse:
        return self

    def __exit__(self, *_: object) -> None:
        return None

    def read(self) -> bytes:
        return self.payload


def test_guardian_client_infers_explicit_demo_header_from_environment(monkeypatch) -> None:
    captured: dict[str, str] = {}

    def fake_urlopen(request: Request, timeout: float) -> FakeResponse:
        assert timeout == 10
        captured.update({key.lower(): value for key, value in request.header_items()})
        return FakeResponse()

    monkeypatch.setenv("GUARDIAN_DEMO_MODE", "true")
    monkeypatch.setattr(client_module, "urlopen", fake_urlopen)

    client = GuardianAPIClient("http://127.0.0.1:8000")
    assert client.get_policy("child-demo") == []
    assert captured["x-guardian-demo"] == "true"


def test_explicit_non_demo_client_does_not_send_demo_header(monkeypatch) -> None:
    captured: dict[str, str] = {}

    def fake_urlopen(request: Request, timeout: float) -> FakeResponse:
        assert timeout == 10
        captured.update({key.lower(): value for key, value in request.header_items()})
        return FakeResponse()

    monkeypatch.setenv("GUARDIAN_DEMO_MODE", "true")
    monkeypatch.setattr(client_module, "urlopen", fake_urlopen)

    client = GuardianAPIClient("http://127.0.0.1:8000", demo_mode=False)
    assert client.get_policy("child-demo") == []
    assert "x-guardian-demo" not in captured
