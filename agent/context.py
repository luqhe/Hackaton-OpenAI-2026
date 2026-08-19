from __future__ import annotations

from collections import defaultdict, deque
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import timedelta

from guardian_core.models import Observation


@dataclass(frozen=True, slots=True)
class ContextKey:
    application: str
    session_id: str


class ObservationContextBuffer:
    """Keeps ephemeral observations isolated by application and session."""

    def __init__(self, *, max_observations: int = 10, max_age_seconds: float = 120) -> None:
        if not 5 <= max_observations <= 10:
            raise ValueError("max_observations must be between 5 and 10")
        if not 0 < max_age_seconds <= 120:
            raise ValueError("max_age_seconds must be greater than 0 and at most 120")
        self._maximum = max_observations
        self._max_age = timedelta(seconds=max_age_seconds)
        self._buffers: dict[ContextKey, deque[Observation]] = defaultdict(lambda: deque(maxlen=self._maximum))

    def add(self, observation: Observation, *, session_id: str = "default") -> ContextKey:
        if not session_id.strip():
            raise ValueError("session_id cannot be blank")
        key = ContextKey(observation.app_name, session_id)
        buffer = self._buffers[key]
        cutoff = observation.timestamp - self._max_age
        while buffer and buffer[0].timestamp < cutoff:
            buffer.popleft()
        buffer.append(observation)
        return key

    def observations(self, key: ContextKey) -> tuple[Observation, ...]:
        return tuple(self._buffers.get(key, ()))

    def sessions(self) -> Iterator[ContextKey]:
        return iter(tuple(self._buffers))

    def clear(self, key: ContextKey) -> None:
        self._buffers.pop(key, None)

    def clear_all(self) -> None:
        self._buffers.clear()
