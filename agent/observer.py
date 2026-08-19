from __future__ import annotations

import platform
import subprocess
import time
from collections.abc import Callable
from pathlib import Path

from PIL import Image


class ObserverPermissionError(RuntimeError):
    """The observer cannot proceed until macOS permissions are restored."""


class PerceptualHash:
    """Compact average hash for detecting meaningful visual changes."""

    SIZE = 8

    @classmethod
    def from_image(cls, screenshot_path: Path) -> str:
        with Image.open(screenshot_path) as image:
            pixels = list(
                image.convert("L")
                .resize(
                    (cls.SIZE, cls.SIZE),
                    Image.Resampling.LANCZOS,
                )
                .tobytes()
            )
        average = sum(pixels) / len(pixels)
        value = 0
        for pixel in pixels:
            value = (value << 1) | int(pixel >= average)
        return f"{value:0{cls.SIZE * cls.SIZE // 4}x}"

    @staticmethod
    def distance(first: str, second: str) -> int:
        return (int(first, 16) ^ int(second, 16)).bit_count()


class MacOSObserver:
    def __init__(
        self,
        *,
        cooldown_seconds: float = 60,
        change_threshold: int = 8,
        initial_hash: str | None = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if platform.system() != "Darwin":
            raise RuntimeError("The real observer is available only on macOS")
        if cooldown_seconds <= 0:
            raise ValueError("cooldown_seconds must be positive")
        if not 0 <= change_threshold <= 64:
            raise ValueError("change_threshold must be between 0 and 64")
        self._last_hash = initial_hash
        self._cooldown_seconds = cooldown_seconds
        self._change_threshold = change_threshold
        self._clock = clock
        self._unavailable_until = 0.0

    def _assert_available(self) -> None:
        remaining = self._unavailable_until - self._clock()
        if remaining > 0:
            raise ObserverPermissionError(
                f"Observer permissions unavailable; retry after {remaining:.0f} seconds."
            )

    def _mark_permission_failure(self) -> None:
        self._unavailable_until = self._clock() + self._cooldown_seconds

    def reset_after_wake(self) -> None:
        """Allow one fresh permission check after the Mac wakes or settings change."""
        self._unavailable_until = 0.0

    def capture_screen(self, destination: Path) -> Path:
        self._assert_available()
        destination.parent.mkdir(parents=True, exist_ok=True)
        try:
            result = subprocess.run(
                ["screencapture", "-x", "-t", "png", str(destination)],
                check=False,
                capture_output=True,
                text=True,
                timeout=10,
            )
        except (OSError, subprocess.TimeoutExpired) as error:
            self._mark_permission_failure()
            raise ObserverPermissionError("Screen capture is temporarily unavailable.") from error
        if result.returncode != 0:
            self._mark_permission_failure()
            raise ObserverPermissionError(
                "Screen Recording permission is missing or was revoked. "
                "Guardian will pause capture before retrying."
            )
        return destination

    def get_active_application(self) -> str:
        self._assert_available()
        script = 'tell application "System Events" to get name of first application process whose frontmost is true'
        try:
            result = subprocess.run(
                ["osascript", "-e", script],
                check=True,
                capture_output=True,
                text=True,
                timeout=5,
            )
        except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as error:
            self._mark_permission_failure()
            raise ObserverPermissionError(
                "Accessibility permission is missing or was revoked. "
                "Guardian will pause observation before retrying."
            ) from error
        return result.stdout.strip()

    def detect_change(self, screenshot_path: Path) -> tuple[bool, str]:
        digest = PerceptualHash.from_image(screenshot_path)
        changed = self._last_hash is None or (
            PerceptualHash.distance(digest, self._last_hash) > self._change_threshold
        )
        self._last_hash = digest
        return changed, digest

    def capture_if_changed(self, destination: Path) -> tuple[Path, str] | None:
        """Capture one frame and discard it immediately when the screen is static."""
        screenshot_path = self.capture_screen(destination)
        changed, digest = self.detect_change(screenshot_path)
        if not changed:
            screenshot_path.unlink(missing_ok=True)
            return None
        return screenshot_path, digest
