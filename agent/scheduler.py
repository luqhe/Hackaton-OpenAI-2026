from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass, field


@dataclass(slots=True)
class AdaptiveObservationSchedule:
    """Computes the next observation interval without owning the event loop."""

    minimum_seconds: float = 10
    maximum_seconds: float = 60
    backoff_factor: float = 1.5
    _current_seconds: float = field(init=False)

    def __post_init__(self) -> None:
        if self.minimum_seconds <= 0:
            raise ValueError("minimum_seconds must be positive")
        if self.maximum_seconds < self.minimum_seconds:
            raise ValueError("maximum_seconds must be greater than or equal to minimum_seconds")
        if self.backoff_factor <= 1:
            raise ValueError("backoff_factor must be greater than 1")
        self._current_seconds = self.minimum_seconds

    @property
    def current_seconds(self) -> float:
        return self._current_seconds

    def report_observation(self, *, changed: bool) -> float:
        if changed:
            self._current_seconds = self.minimum_seconds
        else:
            self._current_seconds = min(
                self.maximum_seconds,
                self._current_seconds * self.backoff_factor,
            )
        return self._current_seconds

    def report_wake(self) -> float:
        self._current_seconds = self.minimum_seconds
        return self._current_seconds


@dataclass(slots=True)
class SuspensionDetector:
    """Detects a likely system sleep from an unexpectedly large monotonic gap."""

    grace_seconds: float = 5
    clock: Callable[[], float] = time.monotonic
    _last_check: float = field(init=False)

    def __post_init__(self) -> None:
        if self.grace_seconds < 0:
            raise ValueError("grace_seconds cannot be negative")
        self._last_check = self.clock()

    def check(self, *, expected_interval: float) -> bool:
        if expected_interval < 0:
            raise ValueError("expected_interval cannot be negative")
        now = self.clock()
        elapsed = now - self._last_check
        self._last_check = now
        return elapsed > expected_interval + self.grace_seconds
