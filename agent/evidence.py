from __future__ import annotations

import tempfile
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from types import TracebackType

from PIL import Image


@dataclass(frozen=True, slots=True)
class EvidenceRegion:
    left: int
    top: int
    right: int
    bottom: int

    def validate(self, image_size: tuple[int, int]) -> None:
        width, height = image_size
        if not (0 <= self.left < self.right <= width):
            raise ValueError("evidence region has invalid horizontal bounds")
        if not (0 <= self.top < self.bottom <= height):
            raise ValueError("evidence region has invalid vertical bounds")


def build_minimal_png(
    source: Path,
    *,
    region: EvidenceRegion | None = None,
    maximum_size: tuple[int, int] = (1280, 720),
) -> bytes:
    """Re-encode selected evidence without metadata and within a privacy size budget."""
    if maximum_size[0] <= 0 or maximum_size[1] <= 0:
        raise ValueError("maximum_size dimensions must be positive")
    with Image.open(source) as original:
        image = original.convert("RGB")
        if region is not None:
            region.validate(image.size)
            image = image.crop((region.left, region.top, region.right, region.bottom))
        image.thumbnail(maximum_size, Image.Resampling.LANCZOS)
        output = BytesIO()
        image.save(output, format="PNG", optimize=True)
        return output.getvalue()


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
