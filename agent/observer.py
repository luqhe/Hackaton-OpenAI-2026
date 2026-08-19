from __future__ import annotations

import hashlib
import platform
import subprocess
from pathlib import Path


class MacOSObserver:
    def __init__(self) -> None:
        if platform.system() != "Darwin":
            raise RuntimeError("The real observer is available only on macOS")
        self._last_hash: str | None = None

    def capture_screen(self, destination: Path) -> Path:
        destination.parent.mkdir(parents=True, exist_ok=True)
        result = subprocess.run(
            ["screencapture", "-x", "-t", "png", str(destination)],
            check=False,
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode != 0:
            raise RuntimeError(
                "Screen capture failed. Grant Screen Recording permission to the terminal running Guardian."
            )
        return destination

    def get_active_application(self) -> str:
        script = 'tell application "System Events" to get name of first application process whose frontmost is true'
        result = subprocess.run(
            ["osascript", "-e", script],
            check=True,
            capture_output=True,
            text=True,
            timeout=5,
        )
        return result.stdout.strip()

    def detect_change(self, screenshot_path: Path) -> tuple[bool, str]:
        digest = hashlib.sha256(screenshot_path.read_bytes()).hexdigest()
        changed = digest != self._last_hash
        self._last_hash = digest
        return changed, digest
