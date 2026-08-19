from __future__ import annotations

from collections import defaultdict, deque
from collections.abc import Iterator
from dataclasses import dataclass

from guardian_core.models import Observation


@dataclass(frozen=True, slots=True)
class ContextKey:
    application: str
    session_id: str


class ObservationContextBuffer:
    """Keeps ephemeral observations isolated by application and session."""

    def __init__(self, *, provisional_max_observations: int = 10) -> None:
        if provisional_max_observations <= 0:
            raise ValueError("provisional_max_observations must be positive")
        self._maximum = provisional_max_observations
        self._buffers: dict[ContextKey, deque[Observation]] = defaultdict(lambda: deque(maxlen=self._maximum))

    def add(self, observation: Observation, *, session_id: str = "default") -> ContextKey:
        if not session_id.strip():
            raise ValueError("session_id cannot be blank")
        key = ContextKey(observation.app_name, session_id)
        self._buffers[key].append(observation)
        return key

    def observations(self, key: ContextKey) -> tuple[Observation, ...]:
        return tuple(self._buffers.get(key, ()))

    def sessions(self) -> Iterator[ContextKey]:
        return iter(tuple(self._buffers))

    def clear(self, key: ContextKey) -> None:
        self._buffers.pop(key, None)

    def clear_all(self) -> None:
        self._buffers.clear()
