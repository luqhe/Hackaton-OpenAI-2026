from __future__ import annotations

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
