import pytest

from agent.evidence import EphemeralCapture


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
