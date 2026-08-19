from __future__ import annotations

import tempfile
from dataclasses import dataclass
from pathlib import Path
from types import TracebackType


@dataclass(slots=True)
class EphemeralCapture:
    """Owns one temporary capture and guarantees idempotent deletion."""

    path: Path

    @classmethod
    def create(cls, *, directory: Path | None = None) -> EphemeralCapture:
        temporary_file = tempfile.NamedTemporaryFile(
            prefix="guardian-",
            suffix=".png",
            dir=directory,
            delete=False,
        )
        temporary_file.close()
        return cls(Path(temporary_file.name))

    def delete(self) -> None:
        self.path.unlink(missing_ok=True)

    def __enter__(self) -> EphemeralCapture:
        return self

    def __exit__(
        self,
        exception_type: type[BaseException] | None,
        exception: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.delete()
