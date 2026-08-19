from __future__ import annotations

import json
import platform
import subprocess
from pathlib import Path

NEVER_BLOCK = frozenset(
    {
        "Activity Monitor",
        "Dock",
        "Finder",
        "Guardian",
        "System Events",
        "System Settings",
        "System Preferences",
        "SystemUIServer",
        "Terminal",
        "iTerm2",
        "guardian-capture-helper",
        "kernel_task",
        "launchd",
        "loginwindow",
        "WindowServer",
    }
)


def normalize_application(application: str) -> str:
    normalized = application.strip().replace("\\", "/").rsplit("/", 1)[-1]
    if normalized.casefold().endswith(".app"):
        normalized = normalized[:-4]
    return normalized.casefold()


PROTECTED_APPLICATIONS = frozenset(normalize_application(item) for item in NEVER_BLOCK)


def is_protected_application(application: str) -> bool:
    return normalize_application(application) in PROTECTED_APPLICATIONS


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
            self.blocked_apps = {
                application
                for application in payload.get("blocked_apps", [])
                if isinstance(application, str) and not is_protected_application(application)
            }
        except (OSError, ValueError, TypeError):
            self.blocked_apps = set()

    def _save(self) -> None:
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        self.state_path.write_text(
            json.dumps({"blocked_apps": sorted(self.blocked_apps)}, indent=2),
            encoding="utf-8",
        )

    def block(self, application: str) -> None:
        if is_protected_application(application):
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
        self.allowed_apps = {
            application for application in allowed_apps if not is_protected_application(application)
        }

    def _assert_allowed(self, application: str) -> None:
        if application not in self.allowed_apps:
            raise ValueError(
                f"{application!r} is not in GUARDIAN_BLOCKABLE_APPS. "
                "Real enforcement is intentionally deny-by-default."
            )

    def _quit(self, application: str) -> None:
        self._assert_allowed(application)
        if not self._is_running(application):
            return
        escaped = application.replace("\\", "\\\\").replace('"', '\\"')
        script = f'tell application "{escaped}" to quit'
        subprocess.run(
            ["osascript", "-e", script],
            check=False,
            capture_output=True,
            text=True,
            timeout=5,
        )

    def _is_running(self, application: str) -> bool:
        self._assert_allowed(application)
        escaped = application.replace("\\", "\\\\").replace('"', '\\"')
        script = (
            'tell application "System Events" to return '
            f'(exists application process whose name is "{escaped}")'
        )
        try:
            result = subprocess.run(
                ["osascript", "-e", script],
                check=False,
                capture_output=True,
                text=True,
                timeout=5,
            )
        except (OSError, subprocess.TimeoutExpired):
            return False
        return result.returncode == 0 and result.stdout.strip().lower() == "true"

    def block(self, application: str) -> None:
        super().block(application)
        self._quit(application)

    def enforce(self) -> None:
        for application in tuple(self.blocked_apps):
            self._quit(application)
