from __future__ import annotations

import hashlib
import hmac
import secrets
from base64 import urlsafe_b64decode, urlsafe_b64encode
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from fastapi import HTTPException, Request, status
from pydantic import BaseModel, ConfigDict, Field

from api.storage import DEMO_ACCOUNT_ID, DEMO_FAMILY_ID, DEMO_MEMBERSHIP_ID
from guardian_core.identity import FamilyScope, MembershipRole

SESSION_COOKIE = "guardian_session"
CSRF_COOKIE = "guardian_csrf"
DEMO_HEADER = "X-Guardian-Demo"
SESSION_TTL = timedelta(hours=8)
PASSWORD_N = 2**14
PASSWORD_R = 8
PASSWORD_P = 1
MAX_LOGIN_ATTEMPTS = 5
LOGIN_WINDOW = timedelta(minutes=15)
PASSWORD_RESET_TTL = timedelta(minutes=30)


class LoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=12, max_length=1024)
    family_id: str | None = Field(default=None, max_length=100)


class SessionResponse(BaseModel):
    account_id: str
    family_id: str
    membership_id: str
    role: MembershipRole


class PasswordRecoveryRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: str = Field(min_length=3, max_length=254)


class PasswordRecoveryComplete(BaseModel):
    model_config = ConfigDict(extra="forbid")

    token: str = Field(min_length=32, max_length=256)
    new_password: str = Field(min_length=12, max_length=1024)


@dataclass(frozen=True, slots=True)
class NewSession:
    scope: FamilyScope
    token: str
    csrf_token: str
    expires_at: datetime


class AuthenticationFailed(Exception):
    pass


class LoginRateLimited(Exception):
    pass


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _encode(value: bytes) -> str:
    return urlsafe_b64encode(value).decode("ascii").rstrip("=")


def _decode(value: str) -> bytes:
    return urlsafe_b64decode(value + "=" * (-len(value) % 4))


def hash_password(password: str) -> str:
    if len(password) < 12:
        raise ValueError("Password must contain at least 12 characters")
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(
        password.encode("utf-8"),
        salt=salt,
        n=PASSWORD_N,
        r=PASSWORD_R,
        p=PASSWORD_P,
        dklen=32,
    )
    return f"scrypt${PASSWORD_N}${PASSWORD_R}${PASSWORD_P}${_encode(salt)}${_encode(digest)}"


def verify_password(password: str, encoded: str) -> bool:
    try:
        algorithm, n, r, p, salt, expected = encoded.split("$", 5)
        parameters = (int(n), int(r), int(p))
        salt_bytes = _decode(salt)
        expected_bytes = _decode(expected)
        if (
            algorithm != "scrypt"
            or parameters != (PASSWORD_N, PASSWORD_R, PASSWORD_P)
            or len(salt_bytes) != 16
            or len(expected_bytes) != 32
        ):
            return False
        digest = hashlib.scrypt(
            password.encode("utf-8"),
            salt=salt_bytes,
            n=parameters[0],
            r=parameters[1],
            p=parameters[2],
            dklen=32,
        )
        return hmac.compare_digest(digest, expected_bytes)
    except (TypeError, ValueError):
        return False


_DUMMY_PASSWORD_HASH = hash_password("guardian dummy password")


def login(store, payload: LoginRequest) -> NewSession:
    identifier = payload.email.strip().casefold()
    identifier_hash = _token_hash(identifier)
    if store.login_attempt_count(identifier_hash, LOGIN_WINDOW) >= MAX_LOGIN_ATTEMPTS:
        raise LoginRateLimited
    credentials = store.get_login_credentials(identifier)
    password_hash = credentials[1] if credentials is not None else _DUMMY_PASSWORD_HASH
    password_valid = verify_password(payload.password, password_hash)
    if credentials is None or not credentials[2] or not password_valid:
        store.record_login_attempt(identifier_hash)
        raise AuthenticationFailed
    scope = store.active_family_scope(credentials[0], payload.family_id)
    if scope is None:
        store.record_login_attempt(identifier_hash)
        raise AuthenticationFailed
    store.clear_login_attempts(identifier_hash)
    token = secrets.token_urlsafe(32)
    csrf_token = secrets.token_urlsafe(32)
    expires_at = datetime.now(UTC) + SESSION_TTL
    store.create_auth_session(
        scope,
        token_hash=_token_hash(token),
        csrf_hash=_token_hash(csrf_token),
        expires_at=expires_at,
    )
    return NewSession(scope=scope, token=token, csrf_token=csrf_token, expires_at=expires_at)


def request_password_reset(
    store,
    email: str,
    notifier: Callable[[str, str], None] | None,
) -> None:
    if notifier is None:
        return
    normalized_email = email.strip().casefold()
    account_id = store.account_id_for_recovery(normalized_email)
    if account_id is None:
        return
    token = secrets.token_urlsafe(32)
    store.create_password_reset_token(
        account_id,
        _token_hash(token),
        datetime.now(UTC) + PASSWORD_RESET_TTL,
    )
    notifier(normalized_email, token)


def complete_password_reset(store, token: str, new_password: str) -> bool:
    return store.consume_password_reset_token(_token_hash(token), hash_password(new_password))


def require_family_scope(request: Request) -> FamilyScope:
    client_host = request.client.host if request.client else ""
    local_transport = client_host in {"127.0.0.1", "::1", "testclient"}
    if (
        request.app.state.settings.demo_mode
        and request.headers.get(DEMO_HEADER) == "true"
        and local_transport
    ):
        request.state.guardian_demo_scope = True
        return FamilyScope(
            account_id=DEMO_ACCOUNT_ID,
            family_id=DEMO_FAMILY_ID,
            membership_id=DEMO_MEMBERSHIP_ID,
            role=MembershipRole.OWNER,
        )
    token = request.cookies.get(SESSION_COOKIE)
    if token:
        scope = request.app.state.store.resolve_family_scope(_token_hash(token))
        if scope is not None:
            return scope
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Authentication required",
    )


def require_mutation_scope(request: Request) -> FamilyScope:
    scope = require_family_scope(request)
    if getattr(request.state, "guardian_demo_scope", False):
        return scope
    session_token = request.cookies.get(SESSION_COOKIE, "")
    csrf_cookie = request.cookies.get(CSRF_COOKIE, "")
    csrf_header = request.headers.get("X-CSRF-Token", "")
    expected_hash = request.app.state.store.auth_session_csrf_hash(_token_hash(session_token))
    if (
        not csrf_cookie
        or not csrf_header
        or not hmac.compare_digest(csrf_cookie, csrf_header)
        or expected_hash is None
        or not hmac.compare_digest(expected_hash, _token_hash(csrf_header))
    ):
        raise HTTPException(status_code=403, detail="CSRF validation failed")
    return scope


def revoke_current_session(request: Request) -> None:
    token = request.cookies.get(SESSION_COOKIE)
    if token:
        request.app.state.store.revoke_auth_session(_token_hash(token))
