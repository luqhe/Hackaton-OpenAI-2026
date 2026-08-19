from __future__ import annotations

import json
import platform
import subprocess
from pathlib import Path


NEVER_BLOCK = {
    "Finder",
    "System Settings",
    "System Preferences",
    "Terminal",
    "iTerm2",
    "loginwindow",
    "WindowServer",
    "Guardian",
}


class DemoEnforcer:
    """Persists blocked-app state without controlling the operating system."""

    def __init__(self, state_path: Path):
        self.state_path = state_path
        self.blocked_apps: set[str] = set()
        self._load()

    def _load(self) -> None:
        if not self.state_path.is_file():
            return
        try:
            payload = json.loads(self.state_path.read_text(encoding="utf-8"))
            self.blocked_apps = set(payload.get("blocked_apps", []))
        except (OSError, ValueError, TypeError):
            self.blocked_apps = set()

    def _save(self) -> None:
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        self.state_path.write_text(
            json.dumps({"blocked_apps": sorted(self.blocked_apps)}, indent=2),
            encoding="utf-8",
        )

    def block(self, application: str) -> None:
        if application in NEVER_BLOCK:
            raise ValueError(f"Guardian refuses to block protected application: {application}")
        self.blocked_apps.add(application)
        self._save()

    def unblock(self, application: str) -> None:
        self.blocked_apps.discard(application)
        self._save()

    def enforce(self) -> None:
        return


class MacOSEnforcer(DemoEnforcer):
    """Minimal, opt-in macOS enforcer for explicitly allow-listed demo apps."""

    def __init__(self, state_path: Path, allowed_apps: set[str]):
        if platform.system() != "Darwin":
            raise RuntimeError("Real enforcement is available only on macOS")
        super().__init__(state_path)
        self.allowed_apps = allowed_apps - NEVER_BLOCK

    def _assert_allowed(self, application: str) -> None:
        if application not in self.allowed_apps:
            raise ValueError(
                f"{application!r} is not in GUARDIAN_BLOCKABLE_APPS. "
                "Real enforcement is intentionally deny-by-default."
            )

    def _quit(self, application: str) -> None:
        self._assert_allowed(application)
        escaped = application.replace('\\', '\\\\').replace('"', '\\"')
        script = f'tell application "{escaped}" to quit'
        subprocess.run(
            ["osascript", "-e", script],
            check=False,
            capture_output=True,
            text=True,
            timeout=5,
        )

    def block(self, application: str) -> None:
        super().block(application)
        self._quit(application)

    def enforce(self) -> None:
        for application in tuple(self.blocked_apps):
            self._quit(application)

