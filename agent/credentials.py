from __future__ import annotations

import json
import subprocess
import sys
from collections.abc import Callable
from typing import Protocol

from guardian_core.device_protocol import IssuedDeviceCredential

KEYCHAIN_SERVICE = "com.guardian.device-credential"
KEYCHAIN_ACCOUNT = "active-device"


class CredentialStorageError(RuntimeError):
    pass


class SecurityCommandError(RuntimeError):
    pass


class CredentialVault(Protocol):
    def save(self, credential: IssuedDeviceCredential) -> None: ...

    def load(self) -> IssuedDeviceCredential: ...

    def delete(self) -> None: ...


SecurityRunner = Callable[[list[str], bytes | None], bytes]


def _run_security(arguments: list[str], stdin: bytes | None) -> bytes:
    try:
        result = subprocess.run(
            ["/usr/bin/security", *arguments],
            input=stdin,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            check=False,
        )
    except OSError as error:
        raise SecurityCommandError("command_unavailable") from error
    if result.returncode != 0:
        raise SecurityCommandError(f"command_failed_{result.returncode}")
    return result.stdout


class MacOSKeychainCredentialVault:
    def __init__(
        self,
        *,
        runner: SecurityRunner = _run_security,
        platform: str = sys.platform,
    ):
        self._runner = runner
        self._platform = platform

    def _ensure_available(self) -> None:
        if self._platform != "darwin":
            raise CredentialStorageError("macOS Keychain is unavailable on this platform")

    def save(self, credential: IssuedDeviceCredential) -> None:
        self._ensure_available()
        payload = json.dumps(
            {
                "credential_id": credential.credential_id,
                "device_id": credential.device_id,
                "public_key": credential.public_key,
                "private_key": credential.private_key,
            },
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
        try:
            self._runner(
                [
                    "add-generic-password",
                    "-U",
                    "-a",
                    KEYCHAIN_ACCOUNT,
                    "-s",
                    KEYCHAIN_SERVICE,
                    "-w",
                ],
                payload + b"\n",
            )
        except SecurityCommandError as error:
            raise CredentialStorageError("could not store device credential in Keychain") from error

    def load(self) -> IssuedDeviceCredential:
        self._ensure_available()
        try:
            payload = self._runner(
                [
                    "find-generic-password",
                    "-a",
                    KEYCHAIN_ACCOUNT,
                    "-s",
                    KEYCHAIN_SERVICE,
                    "-w",
                ],
                None,
            )
        except SecurityCommandError as error:
            raise CredentialStorageError("device credential not found in Keychain") from error
        try:
            value = json.loads(payload)
            return IssuedDeviceCredential(
                credential_id=value["credential_id"],
                device_id=value["device_id"],
                public_key=value["public_key"],
                private_key=value["private_key"],
            )
        except (KeyError, TypeError, UnicodeDecodeError, json.JSONDecodeError) as error:
            raise CredentialStorageError("device credential in Keychain is invalid") from error

    def delete(self) -> None:
        self._ensure_available()
        try:
            self._runner(
                [
                    "delete-generic-password",
                    "-a",
                    KEYCHAIN_ACCOUNT,
                    "-s",
                    KEYCHAIN_SERVICE,
                ],
                None,
            )
        except SecurityCommandError as error:
            raise CredentialStorageError("could not remove device credential from Keychain") from error
