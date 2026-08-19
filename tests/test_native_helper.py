from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
HELPER_ROOT = PROJECT_ROOT / "native" / "GuardianCaptureHelper"


def test_screen_capture_helper_uses_screencapturekit() -> None:
    manifest = (HELPER_ROOT / "Package.swift").read_text(encoding="utf-8")
    source = (HELPER_ROOT / "Sources" / "GuardianCaptureHelper" / "main.swift").read_text(encoding="utf-8")

    assert ".macOS(.v14)" in manifest
    assert "import ScreenCaptureKit" in source
    assert "SCShareableContent" in source
    assert "SCScreenshotManager.captureImage" in source
    assert "configuration.capturesAudio = false" in source
    assert "png.write(to: destination, options: .atomic)" in source
