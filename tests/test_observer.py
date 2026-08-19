from pathlib import Path
from types import SimpleNamespace

import pytest
from PIL import Image

import agent.observer as observer_module
from agent.observer import MacOSObserver, ObserverPermissionError, PerceptualHash


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


def test_perceptual_hash_ignores_png_encoding_differences(monkeypatch, tmp_path: Path) -> None:
    observer = build_observer(monkeypatch, clock=lambda: 0.0)
    first = tmp_path / "first.png"
    second = tmp_path / "second.png"
    image = Image.new("RGB", (80, 80), color=(32, 64, 96))
    image.save(first, compress_level=0)
    image.save(second, compress_level=9)

    assert observer.detect_change(first)[0] is True
    assert observer.detect_change(second)[0] is False


def test_perceptual_hash_detects_meaningful_layout_change(monkeypatch, tmp_path: Path) -> None:
    observer = build_observer(monkeypatch, clock=lambda: 0.0, cooldown_seconds=60)
    first = tmp_path / "first.png"
    second = tmp_path / "second.png"
    Image.new("L", (80, 80), color=255).save(first)
    changed = Image.new("L", (80, 80), color=255)
    for x in range(40):
        for y in range(80):
            changed.putpixel((x, y), 0)
    changed.save(second)

    _, first_hash = observer.detect_change(first)
    is_changed, second_hash = observer.detect_change(second)

    assert is_changed is True
    assert PerceptualHash.distance(first_hash, second_hash) > 8


def test_static_capture_is_deleted_before_analysis(monkeypatch, tmp_path: Path) -> None:
    observer = build_observer(monkeypatch, clock=lambda: 0.0)
    source = Image.new("L", (80, 80), color=255)

    def capture(destination: Path) -> Path:
        source.save(destination)
        return destination

    monkeypatch.setattr(observer, "capture_screen", capture)
    first_path = tmp_path / "first.png"
    static_path = tmp_path / "static.png"

    assert observer.capture_if_changed(first_path) is not None
    assert observer.capture_if_changed(static_path) is None
    assert first_path.exists()
    assert not static_path.exists()
