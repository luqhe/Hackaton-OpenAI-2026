import json

import pytest

from agent.credentials import (
    CredentialStorageError,
    MacOSKeychainCredentialVault,
    SecurityCommandError,
)
from guardian_core.device_protocol import issue_device_credential


class RecordingSecurityRunner:
    def __init__(self):
        self.calls: list[tuple[list[str], bytes | None]] = []
        self.stored: bytes | None = None

    def __call__(self, arguments: list[str], stdin: bytes | None) -> bytes:
        self.calls.append((arguments, stdin))
        if arguments[0] == "add-generic-password":
            assert stdin is not None
            self.stored = stdin.rstrip(b"\n")
            return b""
        if arguments[0] == "find-generic-password":
            if self.stored is None:
                raise SecurityCommandError("item_not_found")
            return self.stored + b"\n"
        if arguments[0] == "delete-generic-password":
            self.stored = None
            return b""
        raise AssertionError(arguments)


def test_keychain_round_trip_keeps_secret_out_of_process_arguments() -> None:
    runner = RecordingSecurityRunner()
    vault = MacOSKeychainCredentialVault(runner=runner, platform="darwin")
    credential = issue_device_credential("device-1")

    vault.save(credential)
    loaded = vault.load()

    assert loaded == credential
    save_arguments, save_stdin = runner.calls[0]
    assert save_arguments[-1] == "-w"
    assert credential.private_key not in " ".join(save_arguments)
    assert credential.private_key in json.loads(save_stdin)["private_key"]


def test_non_macos_fails_without_plaintext_fallback() -> None:
    runner = RecordingSecurityRunner()
    vault = MacOSKeychainCredentialVault(runner=runner, platform="linux")

    with pytest.raises(CredentialStorageError, match="unavailable"):
        vault.save(issue_device_credential("device-1"))

    assert runner.calls == []


def test_keychain_delete_removes_the_credential() -> None:
    runner = RecordingSecurityRunner()
    vault = MacOSKeychainCredentialVault(runner=runner, platform="darwin")
    vault.save(issue_device_credential("device-1"))

    vault.delete()

    with pytest.raises(CredentialStorageError, match="not found"):
        vault.load()
