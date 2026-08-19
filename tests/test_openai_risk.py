import json
from io import BytesIO
from urllib.error import HTTPError, URLError

import pytest

from guardian_core.models import Observation, RiskCategory, RiskLevel
from risk_engine.openai import DEFAULT_MODEL, OpenAIRiskError, assess_screenshot


class FakeResponse:
    def __init__(self, payload: object, status: int = 200):
        self.body = json.dumps(payload).encode("utf-8") if not isinstance(payload, bytes) else payload
        self.status = status

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self, size: int = -1) -> bytes:
        return self.body[:size] if size >= 0 else self.body


def valid_response(assessment: dict | None = None) -> dict:
    result = assessment or {
        "risk": "HIGH",
        "category": "DANGEROUS_CONTACT",
        "direction": "CHILD_AS_TARGET",
        "confidence": 0.93,
        "evidence": ["The chat asks for age, school and a personal photo."],
        "explanation": "Progressive personal-information requests indicate unsafe contact.",
    }
    return {
        "status": "completed",
        "output": [
            {
                "type": "message",
                "content": [{"type": "output_text", "text": json.dumps(result)}],
            }
        ],
    }


@pytest.fixture
def png_path(tmp_path):
    path = tmp_path / "screen.png"
    path.write_bytes(b"\x89PNG\r\n\x1a\nfixture")
    return path


@pytest.fixture
def observation():
    return Observation(app_name="Guardian Demo Chat", window_title="Synthetic Minecraft chat")


def test_valid_response_uses_multimodal_structured_output_without_paid_call(png_path, observation) -> None:
    captured = {}

    def transport(request, timeout):
        captured["request"] = request
        captured["timeout"] = timeout
        return FakeResponse(valid_response())

    result = assess_screenshot(
        png_path,
        observation,
        api_key="test-key",
        transport=transport,
    )

    assert result.risk == RiskLevel.HIGH
    assert result.category == RiskCategory.DANGEROUS_CONTACT
    assert "action" not in result.model_dump()
    request_payload = json.loads(captured["request"].data)
    assert request_payload["model"] == DEFAULT_MODEL
    assert request_payload["store"] is False
    assert request_payload["text"]["format"]["type"] == "json_schema"
    assert request_payload["text"]["format"]["strict"] is True
    schema = request_payload["text"]["format"]["schema"]
    assert schema["additionalProperties"] is False
    assert "action" not in schema["properties"]
    content = request_payload["input"][0]["content"]
    assert content[0]["type"] == "input_text"
    assert "Guardian Demo Chat" in content[0]["text"]
    assert content[1]["type"] == "input_image"
    assert content[1]["image_url"].startswith("data:image/png;base64,")
    assert captured["timeout"] == 20


def test_missing_api_key_stops_before_transport(monkeypatch, png_path, observation) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    def unexpected_transport(*args, **kwargs):
        raise AssertionError("transport must not be called")

    with pytest.raises(OpenAIRiskError, match="OPENAI_API_KEY"):
        assess_screenshot(png_path, observation, transport=unexpected_transport)


@pytest.mark.parametrize(
    ("transport", "message"),
    [
        (
            lambda request, timeout: (_ for _ in ()).throw(
                HTTPError(request.full_url, 429, "rate limited", {}, BytesIO(b"{}"))
            ),
            "HTTP 429",
        ),
        (
            lambda request, timeout: (_ for _ in ()).throw(URLError(TimeoutError())),
            "timed out",
        ),
    ],
)
def test_transport_failures_are_short_and_safe(png_path, observation, transport, message) -> None:
    with pytest.raises(OpenAIRiskError, match=message):
        assess_screenshot(png_path, observation, api_key="test-key", transport=transport)


def test_invalid_http_body_is_rejected(png_path, observation) -> None:
    with pytest.raises(OpenAIRiskError, match="invalid JSON"):
        assess_screenshot(
            png_path,
            observation,
            api_key="test-key",
            transport=lambda request, timeout: FakeResponse(b"not-json"),
        )


def test_invalid_response_shape_is_rejected(png_path, observation) -> None:
    with pytest.raises(OpenAIRiskError, match="invalid response"):
        assess_screenshot(
            png_path,
            observation,
            api_key="test-key",
            transport=lambda request, timeout: FakeResponse({"status": "completed", "output": None}),
        )


def test_refusal_is_rejected(png_path, observation) -> None:
    response = {
        "status": "completed",
        "output": [
            {
                "type": "message",
                "content": [{"type": "refusal", "refusal": "Cannot comply"}],
            }
        ],
    }
    with pytest.raises(OpenAIRiskError, match="refused"):
        assess_screenshot(
            png_path,
            observation,
            api_key="test-key",
            transport=lambda request, timeout: FakeResponse(response),
        )


@pytest.mark.parametrize(
    "assessment",
    [
        {
            "risk": "SAFE",
            "category": "DANGEROUS_CONTACT",
            "direction": None,
            "confidence": 0.9,
            "evidence": [],
            "explanation": "Invalid SAFE semantics.",
        },
        {
            "risk": "HIGH",
            "category": "DANGEROUS_CONTACT",
            "direction": "CHILD_AS_TARGET",
            "confidence": 0.9,
            "evidence": ["signal"],
            "explanation": "Model tried to choose policy.",
            "action": "BLOCK",
        },
    ],
)
def test_invalid_schema_never_becomes_an_assessment(png_path, observation, assessment) -> None:
    with pytest.raises(OpenAIRiskError, match="invalid RiskAssessment"):
        assess_screenshot(
            png_path,
            observation,
            api_key="test-key",
            transport=lambda request, timeout: FakeResponse(valid_response(assessment)),
        )
