from __future__ import annotations

import base64
import binascii
import hashlib
import re
import secrets
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import Protocol
from urllib.parse import unquote_plus, urlsplit

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey

DEVICE_PROTOCOL_VERSION = "1.0"
MAX_CLOCK_SKEW_SECONDS = 120
CREDENTIAL_ID_PATTERN = re.compile(r"cred-[A-Za-z0-9_-]{20,64}\Z")
NONCE_PATTERN = re.compile(r"[A-Za-z0-9_-]{16,128}\Z")
SIGNATURE_PATTERN = re.compile(r"[A-Za-z0-9_-]{86}\Z")
BODY_DIGEST_PATTERN = re.compile(r"[0-9a-f]{64}\Z")


class DeviceCredentialStatus(StrEnum):
    ACTIVE = "ACTIVE"
    ROTATING = "ROTATING"
    REVOKED = "REVOKED"


class DeviceAuthError(ValueError):
    def __init__(self, code: str):
        self.code = code
        super().__init__(f"device authentication failed ({code})")


@dataclass(frozen=True)
class IssuedDeviceCredential:
    credential_id: str
    device_id: str
    public_key: str
    private_key: str = field(repr=False)


@dataclass(frozen=True)
class CredentialRecord:
    credential_id: str
    device_id: str
    family_id: str
    child_id: str
    public_key: str
    status: DeviceCredentialStatus
    expires_at: datetime

    @classmethod
    def from_issued(
        cls,
        credential: IssuedDeviceCredential,
        *,
        family_id: str,
        child_id: str,
        status: DeviceCredentialStatus,
        expires_at: datetime,
    ) -> CredentialRecord:
        return cls(
            credential_id=credential.credential_id,
            device_id=credential.device_id,
            family_id=family_id,
            child_id=child_id,
            public_key=credential.public_key,
            status=status,
            expires_at=expires_at,
        )


@dataclass(frozen=True)
class DevicePrincipal:
    credential_id: str
    device_id: str
    family_id: str
    child_id: str


class CredentialRepository(Protocol):
    def get_credential(self, credential_id: str) -> CredentialRecord | None: ...


class ReplayProtector(Protocol):
    def consume(self, credential_id: str, nonce: str, expires_at: datetime) -> bool: ...


def issue_device_credential(device_id: str) -> IssuedDeviceCredential:
    private_key = Ed25519PrivateKey.generate()
    return IssuedDeviceCredential(
        credential_id=f"cred-{secrets.token_urlsafe(18)}",
        device_id=device_id,
        public_key=_encode_base64url(private_key.public_key().public_bytes_raw()),
        private_key=_encode_base64url(private_key.private_bytes_raw()),
    )


def _encode_base64url(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _decode_base64url(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.b64decode(value + padding, altchars=b"-_", validate=True)


def _body_digest(body: bytes) -> str:
    return hashlib.sha256(body).hexdigest()


def _canonicalize_percent_encoding(component: str) -> str:
    if re.search(r"%(?![0-9A-Fa-f]{2})", component):
        raise ValueError("request target contains invalid percent encoding")
    return re.sub(
        r"%([0-9A-Fa-f]{2})",
        lambda match: f"%{match.group(1).upper()}",
        component,
    )


def canonicalize_target(target: str) -> str:
    split = urlsplit(target)
    if split.scheme or split.netloc or split.fragment or not split.path.startswith("/"):
        raise ValueError("request target must be an absolute path without a fragment")
    path = _canonicalize_percent_encoding(split.path)
    if "\\" in path or re.search(r"%(?:2F|5C)", path, flags=re.IGNORECASE):
        raise ValueError("encoded path separator is ambiguous")
    query_parts = sorted(_canonicalize_percent_encoding(part) for part in split.query.split("&") if part)
    query = "&".join(query_parts)
    return f"{path}?{query}" if query else path


def _canonical_request(
    *,
    method: str,
    target: str,
    timestamp: int,
    nonce: str,
    body_digest: str,
    credential_id: str,
) -> bytes:
    return "\n".join(
        (
            "GUARDIAN-DEVICE-REQUEST-V1",
            method.upper(),
            canonicalize_target(target),
            str(timestamp),
            nonce,
            body_digest,
            credential_id,
        )
    ).encode("utf-8")


def _signature(private_key: str, canonical: bytes) -> str:
    signer = Ed25519PrivateKey.from_private_bytes(_decode_base64url(private_key))
    return _encode_base64url(signer.sign(canonical))


def sign_device_request(
    credential: IssuedDeviceCredential,
    *,
    method: str,
    target: str,
    body: bytes = b"",
    timestamp: datetime,
    nonce: str,
) -> dict[str, str]:
    query_keys = {
        unquote_plus(part.partition("=")[0]).casefold() for part in urlsplit(target).query.split("&") if part
    }
    if credential.private_key in target or query_keys.intersection(
        {"secret", "token", "authorization", "signature", "credential", "private_key"}
    ):
        raise ValueError("secret material is forbidden in request query parameters")
    canonicalize_target(target)
    if timestamp.tzinfo is None:
        raise ValueError("device request timestamp must be timezone-aware")
    if not NONCE_PATTERN.fullmatch(nonce):
        raise ValueError("device request nonce must be 16-128 base64url characters")
    timestamp_seconds = int(timestamp.timestamp())
    body_digest = _body_digest(body)
    canonical = _canonical_request(
        method=method,
        target=target,
        timestamp=timestamp_seconds,
        nonce=nonce,
        body_digest=body_digest,
        credential_id=credential.credential_id,
    )
    return {
        "Authorization": f"GuardianDevice {credential.credential_id}",
        "X-Guardian-Protocol-Version": DEVICE_PROTOCOL_VERSION,
        "X-Guardian-Timestamp": str(timestamp_seconds),
        "X-Guardian-Nonce": nonce,
        "X-Guardian-Content-SHA256": body_digest,
        "X-Guardian-Signature": _signature(credential.private_key, canonical),
    }


class DeviceRequestAuthenticator:
    def __init__(
        self,
        credentials: CredentialRepository,
        replay: ReplayProtector,
        *,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ):
        self.credentials = credentials
        self.replay = replay
        self.clock = clock

    def authenticate(
        self,
        *,
        method: str,
        target: str,
        body: bytes,
        headers: Mapping[str, str],
    ) -> DevicePrincipal:
        normalized_headers = {key.lower(): value for key, value in headers.items()}
        try:
            authorization = normalized_headers["authorization"]
            scheme, credential_id = authorization.split(" ", 1)
        except (KeyError, ValueError) as error:
            raise DeviceAuthError("invalid_credential") from error
        if (
            scheme != "GuardianDevice"
            or not CREDENTIAL_ID_PATTERN.fullmatch(credential_id)
            or len(authorization) > 96
        ):
            raise DeviceAuthError("invalid_credential")
        record = self.credentials.get_credential(credential_id)
        if record is None:
            raise DeviceAuthError("invalid_credential")

        protocol_version = normalized_headers.get("x-guardian-protocol-version")
        if protocol_version != DEVICE_PROTOCOL_VERSION:
            raise DeviceAuthError("unsupported_protocol")
        now = self.clock()
        if record.status == DeviceCredentialStatus.REVOKED:
            raise DeviceAuthError("credential_revoked")
        if now >= record.expires_at:
            raise DeviceAuthError("credential_expired")

        try:
            timestamp_value = normalized_headers["x-guardian-timestamp"]
            nonce = normalized_headers["x-guardian-nonce"]
            body_digest = normalized_headers["x-guardian-content-sha256"]
            supplied_signature = normalized_headers["x-guardian-signature"]
        except (KeyError, ValueError) as error:
            raise DeviceAuthError("malformed_request") from error
        if (
            not re.fullmatch(r"[0-9]{1,12}", timestamp_value)
            or not NONCE_PATTERN.fullmatch(nonce)
            or not BODY_DIGEST_PATTERN.fullmatch(body_digest)
            or not SIGNATURE_PATTERN.fullmatch(supplied_signature)
        ):
            raise DeviceAuthError("malformed_request")
        timestamp = int(timestamp_value)
        if abs(int(now.timestamp()) - timestamp) > MAX_CLOCK_SKEW_SECONDS:
            raise DeviceAuthError("stale_request")
        if not secrets.compare_digest(body_digest, _body_digest(body)):
            raise DeviceAuthError("content_digest_mismatch")
        canonical = _canonical_request(
            method=method,
            target=target,
            timestamp=timestamp,
            nonce=nonce,
            body_digest=body_digest,
            credential_id=credential_id,
        )
        try:
            verifier = Ed25519PublicKey.from_public_bytes(_decode_base64url(record.public_key))
            verifier.verify(_decode_base64url(supplied_signature), canonical)
        except (InvalidSignature, ValueError, binascii.Error):
            raise DeviceAuthError("invalid_signature") from None
        replay_expires_at = datetime.fromtimestamp(timestamp, UTC) + timedelta(seconds=MAX_CLOCK_SKEW_SECONDS)
        if not self.replay.consume(credential_id, nonce, replay_expires_at):
            raise DeviceAuthError("replay_detected")
        return DevicePrincipal(
            credential_id=credential_id,
            device_id=record.device_id,
            family_id=record.family_id,
            child_id=record.child_id,
        )
