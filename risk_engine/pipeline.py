from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import StrEnum

from pydantic import ValidationError

from guardian_core.models import RiskAssessment
from risk_engine.contracts import (
    ClassifierProvider,
    ContextBundle,
    ProviderError,
    ProviderInvalidOutputError,
)
from risk_engine.providers import ConservativeFallbackProvider, HeuristicLocalProvider


class AnalysisSource(StrEnum):
    LOCAL = "LOCAL"
    REMOTE = "REMOTE"
    FALLBACK = "FALLBACK"


@dataclass(frozen=True, slots=True)
class PipelineResult:
    assessment: RiskAssessment
    local_assessment: RiskAssessment
    source: AnalysisSource
    context_digest: str
    provider_version: str
    model_version: str
    prompt_version: str
    remote_attempted: bool
    attempts: int
    eligible_for_automatic_block: bool
    trusted_safe_rule: str | None = None
    errors: tuple[str, ...] = ()


@dataclass(slots=True)
class CircuitBreaker:
    failure_threshold: int = 3
    recovery_seconds: float = 60
    clock: Callable[[], float] = time.monotonic
    consecutive_failures: int = 0
    opened_at: float | None = None

    def allow_request(self) -> bool:
        if self.opened_at is None:
            return True
        if self.clock() - self.opened_at >= self.recovery_seconds:
            self.consecutive_failures = 0
            self.opened_at = None
            return True
        return False

    def record_success(self) -> None:
        self.consecutive_failures = 0
        self.opened_at = None

    def record_failure(self) -> None:
        self.consecutive_failures += 1
        if self.consecutive_failures >= self.failure_threshold:
            self.opened_at = self.clock()


@dataclass(slots=True)
class ContextualRiskPipeline:
    remote_provider: ClassifierProvider | None
    local_provider: HeuristicLocalProvider = field(default_factory=HeuristicLocalProvider)
    fallback_provider: ConservativeFallbackProvider = field(default_factory=ConservativeFallbackProvider)
    timeout_seconds: float = 20
    max_attempts: int = 2
    circuit_breaker: CircuitBreaker = field(default_factory=CircuitBreaker)

    def __post_init__(self) -> None:
        if self.timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be greater than zero")
        if not 1 <= self.max_attempts <= 3:
            raise ValueError("max_attempts must be between one and three")

    def assess(self, context: ContextBundle) -> PipelineResult:
        local = self.local_provider.classify(context, timeout=self.timeout_seconds)
        safe_rule = self.local_provider.trusted_safe_rule(context, local)
        if safe_rule:
            descriptor = self.local_provider.descriptor
            return PipelineResult(
                assessment=local,
                local_assessment=local,
                source=AnalysisSource.LOCAL,
                context_digest=context.context_digest,
                provider_version=descriptor.provider_version,
                model_version=descriptor.model_version,
                prompt_version=descriptor.prompt_version,
                remote_attempted=False,
                attempts=0,
                eligible_for_automatic_block=False,
                trusted_safe_rule=safe_rule,
            )

        errors: list[str] = []
        attempts = 0
        if self.remote_provider is not None and self.circuit_breaker.allow_request():
            for _ in range(self.max_attempts):
                attempts += 1
                try:
                    raw = self.remote_provider.classify(context, timeout=self.timeout_seconds)
                    remote = RiskAssessment.model_validate(raw)
                except (ValidationError, TypeError, ValueError):
                    self.circuit_breaker.record_failure()
                    errors.append(ProviderInvalidOutputError.__name__)
                    break
                except ProviderError as error:
                    self.circuit_breaker.record_failure()
                    errors.append(type(error).__name__)
                    if not error.retryable:
                        break
                except Exception:
                    self.circuit_breaker.record_failure()
                    errors.append("UnexpectedProviderError")
                    break
                else:
                    self.circuit_breaker.record_success()
                    descriptor = self.remote_provider.descriptor
                    return PipelineResult(
                        assessment=remote,
                        local_assessment=local,
                        source=AnalysisSource.REMOTE,
                        context_digest=context.context_digest,
                        provider_version=descriptor.provider_version,
                        model_version=descriptor.model_version,
                        prompt_version=descriptor.prompt_version,
                        remote_attempted=True,
                        attempts=attempts,
                        eligible_for_automatic_block=True,
                    )
        elif self.remote_provider is not None:
            errors.append("CircuitBreakerOpen")

        fallback = self.fallback_provider.classify_from_local(local)
        descriptor = self.fallback_provider.descriptor
        return PipelineResult(
            assessment=fallback,
            local_assessment=local,
            source=AnalysisSource.FALLBACK,
            context_digest=context.context_digest,
            provider_version=descriptor.provider_version,
            model_version=descriptor.model_version,
            prompt_version=descriptor.prompt_version,
            remote_attempted=attempts > 0,
            attempts=attempts,
            eligible_for_automatic_block=False,
            errors=tuple(errors),
        )
