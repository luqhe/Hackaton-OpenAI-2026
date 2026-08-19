from io import BytesIO

import pytest
from PIL import Image, PngImagePlugin

from agent.evidence import EphemeralCapture, EvidenceRegion, build_minimal_png


def test_ephemeral_capture_deletes_file_on_normal_exit(tmp_path) -> None:
    with EphemeralCapture.create(directory=tmp_path) as capture:
        capture.path.write_bytes(b"temporary")
        assert capture.path.exists()

    assert not capture.path.exists()


def test_ephemeral_capture_deletes_file_after_exception(tmp_path) -> None:
    with pytest.raises(RuntimeError, match="analysis failed"):
        with EphemeralCapture.create(directory=tmp_path) as capture:
            capture.path.write_bytes(b"temporary")
            raise RuntimeError("analysis failed")

    assert not capture.path.exists()


def test_ephemeral_capture_delete_is_idempotent(tmp_path) -> None:
    capture = EphemeralCapture.create(directory=tmp_path)

    capture.delete()
    capture.delete()

    assert not capture.path.exists()


def test_minimal_evidence_is_resized_and_metadata_is_removed(tmp_path) -> None:
    source = tmp_path / "source.png"
    metadata = PngImagePlugin.PngInfo()
    metadata.add_text("sensitive", "must not survive")
    Image.new("RGB", (2000, 1000), color="navy").save(source, pnginfo=metadata)

    payload = build_minimal_png(source)
    with Image.open(BytesIO(payload)) as evidence:
        assert evidence.width <= 1280
        assert evidence.height <= 720
        assert "sensitive" not in evidence.info


def test_minimal_evidence_can_crop_selected_region(tmp_path) -> None:
    source = tmp_path / "source.png"
    Image.new("RGB", (800, 600), color="white").save(source)

    payload = build_minimal_png(
        source,
        region=EvidenceRegion(left=100, top=150, right=400, bottom=350),
    )

    with Image.open(BytesIO(payload)) as evidence:
        assert evidence.size == (300, 200)


def test_minimal_evidence_rejects_region_outside_frame(tmp_path) -> None:
    source = tmp_path / "source.png"
    Image.new("RGB", (100, 100), color="white").save(source)

    with pytest.raises(ValueError, match="horizontal bounds"):
        build_minimal_png(source, region=EvidenceRegion(0, 0, 101, 50))
