from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field

from guardian_core.models import Observation, RiskAssessment

CLASSIFIER_INTERFACE_VERSION = "guardian.classifier.v1"


class ProviderDescriptor(BaseModel):
    """Immutable identity used by evals, release gates and audit records."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    interface_version: str = CLASSIFIER_INTERFACE_VERSION
    provider: str = Field(min_length=1, max_length=80)
    provider_version: str = Field(min_length=1, max_length=80)
    model_version: str = Field(min_length=1, max_length=120)
    prompt_version: str = Field(min_length=1, max_length=120)


@dataclass(frozen=True, slots=True)
class ContextBundle:
    """Normalized input. All observed fields remain explicitly untrusted."""

    observation: Observation
    ocr_text: str
    untrusted_payload: str
    context_digest: str
    selected_frame_path: Path | None = None
    selected_frame_sha256: str | None = None


class ProviderError(RuntimeError):
    """Expected provider failure with a stable retry classification."""

    retryable = False


class ProviderTimeoutError(ProviderError):
    retryable = True


class ProviderUnavailableError(ProviderError):
    retryable = True


class ProviderInvalidOutputError(ProviderError):
    retryable = False


@runtime_checkable
class ClassifierProvider(Protocol):
    """Versioned interface implemented by local, remote and fallback providers."""

    descriptor: ProviderDescriptor

    def classify(self, context: ContextBundle, *, timeout: float) -> RiskAssessment: ...
