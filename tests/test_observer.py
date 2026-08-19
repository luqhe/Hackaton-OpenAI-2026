from pathlib import Path
from types import SimpleNamespace

import pytest

import agent.observer as observer_module
from agent.observer import MacOSObserver, ObserverPermissionError


def build_observer(monkeypatch, *, clock, cooldown_seconds=60):
    monkeypatch.setattr(observer_module.platform, "system", lambda: "Darwin")
    return MacOSObserver(cooldown_seconds=cooldown_seconds, clock=clock)


def test_revoked_screen_permission_opens_circuit_without_retry_loop(monkeypatch, tmp_path: Path) -> None:
    now = [100.0]
    calls = []
    observer = build_observer(monkeypatch, clock=lambda: now[0])

    def denied_capture(*args, **kwargs):
        calls.append((args, kwargs))
        return SimpleNamespace(returncode=1)

    monkeypatch.setattr(observer_module.subprocess, "run", denied_capture)

    with pytest.raises(ObserverPermissionError, match="revoked"):
        observer.capture_screen(tmp_path / "frame.png")
    with pytest.raises(ObserverPermissionError, match="retry after 60 seconds"):
        observer.capture_screen(tmp_path / "frame.png")

    assert len(calls) == 1


def test_permission_circuit_allows_recheck_after_cooldown(monkeypatch, tmp_path: Path) -> None:
    now = [100.0]
    results = iter([SimpleNamespace(returncode=1), SimpleNamespace(returncode=0)])
    observer = build_observer(monkeypatch, clock=lambda: now[0], cooldown_seconds=10)
    monkeypatch.setattr(observer_module.subprocess, "run", lambda *args, **kwargs: next(results))

    with pytest.raises(ObserverPermissionError):
        observer.capture_screen(tmp_path / "frame.png")
    now[0] += 10

    assert observer.capture_screen(tmp_path / "frame.png") == tmp_path / "frame.png"


def test_reset_after_wake_rearms_permission_probe(monkeypatch, tmp_path: Path) -> None:
    now = [100.0]
    results = iter([SimpleNamespace(returncode=1), SimpleNamespace(returncode=0)])
    observer = build_observer(monkeypatch, clock=lambda: now[0])
    monkeypatch.setattr(observer_module.subprocess, "run", lambda *args, **kwargs: next(results))

    with pytest.raises(ObserverPermissionError):
        observer.capture_screen(tmp_path / "frame.png")
    observer.reset_after_wake()

    assert observer.capture_screen(tmp_path / "frame.png") == tmp_path / "frame.png"
