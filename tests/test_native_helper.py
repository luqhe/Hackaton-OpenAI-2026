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


def test_native_helper_reads_frontmost_application_and_window() -> None:
    source = (HELPER_ROOT / "Sources" / "GuardianCaptureHelper" / "main.swift").read_text(encoding="utf-8")

    assert "NSWorkspace.shared.frontmostApplication" in source
    assert "CGWindowListCopyWindowInfo" in source
    assert "kCGWindowOwnerPID" in source
    assert 'case "active-window"' in source
    assert "application.bundleIdentifier" in source


def test_native_helper_performs_local_vision_ocr() -> None:
    source = (HELPER_ROOT / "Sources" / "GuardianCaptureHelper" / "main.swift").read_text(encoding="utf-8")

    assert "import Vision" in source
    assert "VNRecognizeTextRequest" in source
    assert "request.recognitionLevel = .accurate" in source
    assert "request.usesLanguageCorrection = true" in source
    assert "VNImageRequestHandler" in source
    assert 'case "ocr"' in source


def test_native_helper_handles_display_topology_and_sleep() -> None:
    source = (HELPER_ROOT / "Sources" / "GuardianCaptureHelper" / "main.swift").read_text(encoding="utf-8")

    assert "content.displays.first(where:" in source
    assert "CGMainDisplayID()" in source
    assert "CGDisplayIsOnline" in source
    assert "CGDisplayIsAsleep" in source
    assert "configuration.width = display.width" in source
    assert "configuration.height = display.height" in source
    assert 'case "displays"' in source
    assert 'arguments[3] == "--display-id"' in source


def test_native_helper_has_explicit_permission_onboarding() -> None:
    source = (HELPER_ROOT / "Sources" / "GuardianCaptureHelper" / "main.swift").read_text(encoding="utf-8")
    guide = (PROJECT_ROOT / "docs" / "product" / "macos-permissions.md").read_text(encoding="utf-8")

    assert "CGPreflightScreenCaptureAccess" in source
    assert "CGRequestScreenCaptureAccess" in source
    assert "AXIsProcessTrustedWithOptions" in source
    assert 'case "permissions"' in source
    assert 'arguments[2] == "--request"' in source
    assert "Gravação da Tela" in guide
    assert "Acessibilidade" in guide
    assert "câmera e o microfone não são solicitados" in guide
