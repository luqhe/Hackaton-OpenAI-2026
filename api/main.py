from __future__ import annotations

import asyncio
import secrets
import sqlite3
from collections.abc import Callable
from contextlib import asynccontextmanager
from datetime import UTC, date, datetime
from pathlib import Path

from fastapi import Body, Depends, FastAPI, HTTPException, Query, Request, Response, status
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from api.auth import (
    CSRF_COOKIE,
    SESSION_COOKIE,
    SESSION_TTL,
    AuthenticationFailed,
    LoginRateLimited,
    LoginRequest,
    PasswordRecoveryComplete,
    PasswordRecoveryRequest,
    SessionResponse,
    complete_password_reset,
    login,
    request_password_reset,
    require_family_scope,
    require_mutation_scope,
    revoke_current_session,
)
from api.device_identity import DeviceIdentityStore, PairingError
from api.storage import GuardianStore
from guardian_core.config import GuardianSettings
from guardian_core.device_api import (
    AgentIncidentCreate,
    AgentTelemetryUpdate,
    CommandAcknowledgement,
    CredentialRotationRequest,
    DeviceCredentialIssued,
    PairingChallengeCreate,
    PairingChallengeIssued,
    PairingConfirmation,
)
from guardian_core.device_protocol import DeviceAuthError, DevicePrincipal, DeviceRequestAuthenticator
from guardian_core.identity import FamilyScope
from guardian_core.models import (
    DailyReport,
    Device,
    DeviceCommand,
    DeviceHeartbeat,
    DevicePairRequest,
    Incident,
    IncidentCreate,
    IncidentStatus,
    PolicyRule,
    ProductCapabilities,
    TelemetryUpdate,
    UnlockRequest,
)
from guardian_core.version import API_VERSION, APP_VERSION

PROJECT_ROOT = Path(__file__).resolve().parents[1]
WEB_ROOT = PROJECT_ROOT / "web"
ALLOWED_EVIDENCE_TYPES = {"image/png", "image/jpeg", "image/webp", "text/plain"}
MAX_EVIDENCE_BYTES = 4 * 1024 * 1024


def create_app(
    database_path: Path | None = None,
    evidence_directory: Path | None = None,
    settings: GuardianSettings | None = None,
    password_reset_notifier: Callable[[str, str], None] | None = None,
    family_scope_resolver: Callable[[Request], FamilyScope] | None = None,
    device_clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    pairing_pepper: bytes | None = None,
) -> FastAPI:
    runtime_settings = settings or GuardianSettings.from_env()
    db_path = database_path or runtime_settings.database_path
    evidence_path = evidence_directory or runtime_settings.evidence_directory
    store = GuardianStore(
        db_path,
        evidence_path,
        environment=runtime_settings.environment,
        demo_mode=runtime_settings.demo_mode,
    )
    if pairing_pepper is None:
        if runtime_settings.environment in {"staging", "production"}:
            raise RuntimeError("pairing pepper is required outside development/test")
        pairing_pepper = secrets.token_bytes(32)
    device_store = DeviceIdentityStore(store, pairing_pepper=pairing_pepper, clock=device_clock)
    device_authenticator = DeviceRequestAuthenticator(device_store, device_store, clock=device_clock)

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        store.initialize()
        device_store.initialize()
        yield

    app = FastAPI(
        title="Guardian API",
        version=APP_VERSION,
        description="Local control plane for the Guardian hackathon vertical slice.",
        lifespan=lifespan,
    )
    app.state.store = store
    app.state.settings = runtime_settings
    app.state.device_store = device_store

    def require_demo_agent_route() -> None:
        if not runtime_settings.demo_mode:
            raise HTTPException(status_code=404, detail="Resource not found")

    def parent_scope(request: Request) -> FamilyScope:
        if family_scope_resolver is not None:
            return family_scope_resolver(request)
        return require_mutation_scope(request)

    def _request_target(request: Request) -> str:
        raw_path = request.scope.get("raw_path", request.url.path.encode("ascii")).decode("ascii")
        query = request.scope.get("query_string", b"").decode("ascii")
        return f"{raw_path}?{query}" if query else raw_path

    async def device_principal(request: Request) -> DevicePrincipal:
        try:
            return device_authenticator.authenticate(
                method=request.method,
                target=_request_target(request),
                body=await request.body(),
                headers=request.headers,
            )
        except DeviceAuthError as error:
            response_status = 426 if error.code == "unsupported_protocol" else 401
            if error.code == "replay_detected":
                response_status = 409
            raise HTTPException(
                status_code=response_status,
                detail=error.code,
                headers={"Cache-Control": "no-store", "WWW-Authenticate": "GuardianDevice"},
            ) from None

    @app.post(
        "/api/pairing/challenges",
        response_model=PairingChallengeIssued,
        status_code=status.HTTP_201_CREATED,
    )
    def create_pairing_challenge(
        payload: PairingChallengeCreate, scope: FamilyScope = Depends(parent_scope)
    ) -> dict[str, object]:
        try:
            return device_store.create_pairing_challenge(scope, payload.child_id)
        except KeyError:
            raise HTTPException(status_code=404, detail="Child not found") from None

    @app.post(
        "/api/device/pair",
        response_model=DeviceCredentialIssued,
        status_code=status.HTTP_201_CREATED,
    )
    def confirm_pairing(payload: PairingConfirmation) -> DeviceCredentialIssued:
        try:
            return device_store.complete_pairing(payload)
        except PairingError:
            raise HTTPException(status_code=410, detail="invalid_or_expired_pairing") from None

    @app.post("/api/devices/{device_id}/credentials/revoke", status_code=status.HTTP_204_NO_CONTENT)
    def revoke_device_credential(device_id: str, scope: FamilyScope = Depends(parent_scope)) -> Response:
        try:
            device_store.revoke_device(scope, device_id)
        except KeyError:
            raise HTTPException(status_code=404, detail="Device not found") from None
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    @app.post("/api/agent/credentials/rotate", response_model=DeviceCredentialIssued)
    def rotate_device_credential(
        payload: CredentialRotationRequest,
        principal: DevicePrincipal = Depends(device_principal),
    ) -> DeviceCredentialIssued:
        try:
            return device_store.rotate_credential(principal, payload.public_key, payload.idempotency_key)
        except PairingError as error:
            if error.code == "idempotency_conflict":
                raise HTTPException(status_code=409, detail=error.code) from None
            raise HTTPException(status_code=422, detail=error.code) from None

    @app.get("/api/agent/policy", response_model=list[PolicyRule])
    def authenticated_policy(
        principal: DevicePrincipal = Depends(device_principal),
    ) -> list[PolicyRule]:
        return store.get_policy(principal.family_id, principal.child_id)

    @app.post("/api/agent/incidents", response_model=Incident, status_code=status.HTTP_201_CREATED)
    def authenticated_incident(
        payload: AgentIncidentCreate,
        response: Response,
        principal: DevicePrincipal = Depends(device_principal),
    ) -> Incident:
        request = IncidentCreate(
            child_id=principal.child_id,
            device_id=principal.device_id,
            **payload.model_dump(),
        )
        incident, created = store.create_incident(principal.family_id, request)
        response.headers["X-Guardian-Deduplicated"] = "false" if created else "true"
        if not created:
            response.status_code = status.HTTP_200_OK
        return incident

    @app.post("/api/agent/telemetry", status_code=status.HTTP_204_NO_CONTENT)
    def authenticated_telemetry(
        payload: AgentTelemetryUpdate,
        principal: DevicePrincipal = Depends(device_principal),
    ) -> Response:
        store.record_telemetry(
            principal.family_id,
            principal.device_id,
            TelemetryUpdate(child_id=principal.child_id, **payload.model_dump()),
        )
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    @app.post(
        "/api/agent/incidents/{incident_id}/evidence",
        status_code=status.HTTP_201_CREATED,
    )
    async def authenticated_evidence(
        incident_id: str,
        request: Request,
        principal: DevicePrincipal = Depends(device_principal),
    ) -> dict[str, str]:
        if not device_store.incident_belongs_to_device(principal, incident_id):
            raise HTTPException(status_code=404, detail="Incident not found")
        content_type = request.headers.get("content-type", "").split(";", 1)[0].lower()
        if content_type not in ALLOWED_EVIDENCE_TYPES:
            raise HTTPException(status_code=415, detail="Unsupported evidence type")
        data = await request.body()
        if not data:
            raise HTTPException(status_code=422, detail="Evidence body cannot be empty")
        if len(data) > MAX_EVIDENCE_BYTES:
            raise HTTPException(status_code=413, detail="Evidence exceeds the 4 MB limit")
        evidence_id = store.save_evidence(principal.family_id, incident_id, data, content_type)
        return {"id": evidence_id, "url": f"/api/evidence/{evidence_id}"}

    @app.get("/api/agent/commands", response_model=list[DeviceCommand])
    async def authenticated_commands(
        after_id: int = Query(default=0, ge=0),
        wait_seconds: float = Query(default=20, ge=0, le=25),
        principal: DevicePrincipal = Depends(device_principal),
    ) -> list[DeviceCommand]:
        deadline = asyncio.get_running_loop().time() + wait_seconds
        while True:
            commands = device_store.pending_commands(principal, after_id)
            if commands or asyncio.get_running_loop().time() >= deadline:
                return commands
            await asyncio.sleep(min(0.25, max(0, deadline - asyncio.get_running_loop().time())))

    @app.post("/api/agent/commands/{command_id}/ack", response_model=DeviceCommand)
    def authenticated_command_ack(
        command_id: int,
        payload: CommandAcknowledgement,
        principal: DevicePrincipal = Depends(device_principal),
    ) -> DeviceCommand:
        try:
            return device_store.acknowledge_command(principal, command_id, payload)
        except KeyError:
            raise HTTPException(status_code=404, detail="Command not found") from None
        except ValueError as error:
            raise HTTPException(status_code=409, detail=str(error)) from None

    @app.middleware("http")
    async def security_headers(request: Request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["X-Frame-Options"] = "SAMEORIGIN"
        response.headers["X-Guardian-API-Version"] = API_VERSION
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; connect-src 'self'; img-src 'self' data:; "
            "style-src 'self' 'unsafe-inline'; script-src 'self'; frame-src 'self'; "
            "object-src 'none'; base-uri 'none'; form-action 'self'"
        )
        return response

    @app.get("/api/health")
    def health() -> dict[str, str]:
        return {
            "status": "ok",
            "service": "guardian-api",
            "version": app.version,
            "api_version": API_VERSION,
            "environment": runtime_settings.environment,
        }

    @app.get("/api/capabilities", response_model=ProductCapabilities)
    def capabilities() -> ProductCapabilities:
        demo_scope = (
            "FIXTURES_ONLY"
            if runtime_settings.environment in {"development", "test"}
            and runtime_settings.automatic_blocking_enabled
            else "DISABLED"
        )
        return ProductCapabilities(
            environment=runtime_settings.environment,
            api_version=API_VERSION,
            fixture_analysis=True,
            real_screen_observation=False,
            local_ocr=False,
            system_audio=False,
            microphone=False,
            camera=False,
            simulated_enforcement=True,
            real_macos_enforcement=False,
            automatic_blocking_scope=demo_scope,
            authentication=True,
            tenant_isolation=True,
            production_ready=False,
            notes=[
                "Current observation input is limited to controlled fixtures.",
                "Account sessions and family isolation are implemented; device credentials are pending.",
                "The real-enforcement setting is an authorization gate, not proof of an active agent.",
            ],
        )

    @app.post("/api/auth/login", response_model=SessionResponse)
    def login_account(payload: LoginRequest, response: Response) -> SessionResponse:
        try:
            session = login(store, payload)
        except AuthenticationFailed:
            raise HTTPException(status_code=401, detail="Invalid credentials") from None
        except LoginRateLimited:
            raise HTTPException(status_code=429, detail="Too many login attempts") from None
        secure = runtime_settings.environment in {"staging", "production"}
        max_age = int(SESSION_TTL.total_seconds())
        response.set_cookie(
            SESSION_COOKIE,
            session.token,
            max_age=max_age,
            expires=session.expires_at,
            secure=secure,
            httponly=True,
            samesite="strict",
            path="/",
        )
        response.set_cookie(
            CSRF_COOKIE,
            session.csrf_token,
            max_age=max_age,
            expires=session.expires_at,
            secure=secure,
            httponly=False,
            samesite="strict",
            path="/",
        )
        return SessionResponse(
            account_id=session.scope.account_id,
            family_id=session.scope.family_id,
            membership_id=session.scope.membership_id,
            role=session.scope.role,
        )

    @app.get("/api/auth/session", response_model=SessionResponse)
    def current_session(scope: FamilyScope = Depends(require_family_scope)) -> SessionResponse:
        return SessionResponse(
            account_id=scope.account_id,
            family_id=scope.family_id,
            membership_id=scope.membership_id,
            role=scope.role,
        )

    @app.post("/api/auth/recovery", status_code=status.HTTP_202_ACCEPTED)
    def start_password_recovery(payload: PasswordRecoveryRequest) -> dict[str, str]:
        request_password_reset(store, payload.email, password_reset_notifier)
        return {"detail": "If the account is eligible, recovery instructions were sent"}

    @app.post("/api/auth/recovery/complete", status_code=status.HTTP_204_NO_CONTENT)
    def finish_password_recovery(payload: PasswordRecoveryComplete) -> Response:
        if not complete_password_reset(store, payload.token, payload.new_password):
            raise HTTPException(status_code=400, detail="Invalid or expired recovery token")
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    def clear_auth_cookies(response: Response) -> None:
        response.delete_cookie(SESSION_COOKIE, path="/")
        response.delete_cookie(CSRF_COOKIE, path="/")

    @app.post("/api/auth/logout", status_code=status.HTTP_204_NO_CONTENT)
    def logout(
        request: Request,
        response: Response,
        _: FamilyScope = Depends(require_mutation_scope),
    ) -> Response:
        revoke_current_session(request)
        clear_auth_cookies(response)
        response.status_code = status.HTTP_204_NO_CONTENT
        return response

    @app.post("/api/auth/logout-all", status_code=status.HTTP_204_NO_CONTENT)
    def logout_all(
        response: Response,
        scope: FamilyScope = Depends(require_mutation_scope),
    ) -> Response:
        store.revoke_account_sessions(scope.account_id)
        clear_auth_cookies(response)
        response.status_code = status.HTTP_204_NO_CONTENT
        return response

    @app.post("/api/devices/pair", response_model=Device, status_code=status.HTTP_201_CREATED)
    def pair_device(
        payload: DevicePairRequest,
        scope: FamilyScope = Depends(parent_scope),
    ) -> Device:
        require_demo_agent_route()
        if not store.child_exists(scope.family_id, payload.child_id):
            raise HTTPException(status_code=404, detail="Resource not found")
        return store.pair_device(scope.family_id, payload)

    @app.get("/api/devices/{device_id}", response_model=Device)
    def get_device(device_id: str, scope: FamilyScope = Depends(require_family_scope)) -> Device:
        try:
            return store.get_device(scope.family_id, device_id)
        except KeyError:
            raise HTTPException(status_code=404, detail="Resource not found") from None

    @app.post("/api/devices/{device_id}/heartbeat", response_model=Device)
    def record_heartbeat(device_id: str, payload: DeviceHeartbeat) -> Device:
        try:
            return store.record_heartbeat(device_id, payload)
        except KeyError:
            raise HTTPException(status_code=404, detail="Device not found") from None

    @app.get("/api/children/{child_id}/policy", response_model=list[PolicyRule])
    def get_policy(child_id: str, scope: FamilyScope = Depends(require_family_scope)) -> list[PolicyRule]:
        if not store.child_exists(scope.family_id, child_id):
            raise HTTPException(status_code=404, detail="Resource not found")
        return store.get_policy(scope.family_id, child_id)

    @app.put("/api/children/{child_id}/policy", response_model=list[PolicyRule])
    def replace_policy(
        child_id: str,
        rules: list[PolicyRule] = Body(min_length=1, max_length=20),
        scope: FamilyScope = Depends(parent_scope),
    ) -> list[PolicyRule]:
        if not store.child_exists(scope.family_id, child_id):
            raise HTTPException(status_code=404, detail="Resource not found")
        if len({rule.category for rule in rules}) != len(rules):
            raise HTTPException(status_code=422, detail="Policy categories must be unique")
        return store.replace_policy(scope.family_id, child_id, rules)

    @app.post("/api/incidents", response_model=Incident, status_code=status.HTTP_201_CREATED)
    def create_incident(
        payload: IncidentCreate,
        response: Response,
        scope: FamilyScope = Depends(parent_scope),
    ) -> Incident:
        if not store.child_exists(scope.family_id, payload.child_id):
            raise HTTPException(status_code=404, detail="Resource not found")
        if not store.device_exists(scope.family_id, payload.device_id):
            raise HTTPException(status_code=404, detail="Resource not found")
        try:
            incident, created = store.create_incident(scope.family_id, payload)
        except KeyError:
            raise HTTPException(status_code=404, detail="Resource not found") from None
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error)) from None
        except sqlite3.IntegrityError as error:
            raise HTTPException(status_code=409, detail="Incident references invalid data") from error
        response.headers["X-Guardian-Deduplicated"] = "false" if created else "true"
        if not created:
            response.status_code = status.HTTP_200_OK
        return incident

    @app.get("/api/incidents", response_model=list[Incident])
    def list_incidents(
        child_id: str = Query(min_length=1, max_length=100),
        limit: int = Query(default=20, ge=1, le=100),
        incident_status: IncidentStatus | None = Query(default=None, alias="status"),
        scope: FamilyScope = Depends(require_family_scope),
    ) -> list[Incident]:
        try:
            return store.list_incidents(scope.family_id, child_id, limit, incident_status)
        except KeyError:
            raise HTTPException(status_code=404, detail="Resource not found") from None

    @app.get("/api/incidents/{incident_id}", response_model=Incident)
    def get_incident(incident_id: str, scope: FamilyScope = Depends(require_family_scope)) -> Incident:
        try:
            return store.get_incident(scope.family_id, incident_id)
        except KeyError:
            raise HTTPException(status_code=404, detail="Resource not found") from None

    @app.post("/api/incidents/{incident_id}/request-unlock", response_model=Incident)
    def request_unlock(
        incident_id: str,
        payload: UnlockRequest,
        scope: FamilyScope = Depends(parent_scope),
    ) -> Incident:
        try:
            return store.request_unlock(scope.family_id, incident_id, payload.explanation)
        except KeyError:
            raise HTTPException(status_code=404, detail="Resource not found") from None
        except ValueError as error:
            raise HTTPException(status_code=409, detail=str(error)) from None

    @app.post("/api/incidents/{incident_id}/unlock", response_model=Incident)
    def unlock(
        incident_id: str,
        scope: FamilyScope = Depends(parent_scope),
    ) -> Incident:
        try:
            return store.unlock_incident(
                scope.family_id,
                incident_id,
                command_created_at=device_clock(),
            )
        except KeyError:
            raise HTTPException(status_code=404, detail="Resource not found") from None
        except ValueError as error:
            raise HTTPException(status_code=409, detail=str(error)) from None

    @app.post("/api/incidents/{incident_id}/keep-blocked", response_model=Incident)
    def keep_blocked(
        incident_id: str,
        scope: FamilyScope = Depends(parent_scope),
    ) -> Incident:
        try:
            return store.keep_blocked(scope.family_id, incident_id)
        except KeyError:
            raise HTTPException(status_code=404, detail="Resource not found") from None
        except ValueError as error:
            raise HTTPException(status_code=409, detail=str(error)) from None

    @app.post("/api/incidents/{incident_id}/evidence", status_code=status.HTTP_201_CREATED)
    async def upload_evidence(
        incident_id: str,
        request: Request,
        scope: FamilyScope = Depends(parent_scope),
    ) -> dict[str, str]:
        content_type = request.headers.get("content-type", "").split(";", 1)[0].lower()
        if content_type not in ALLOWED_EVIDENCE_TYPES:
            raise HTTPException(status_code=415, detail="Unsupported evidence type")
        data = await request.body()
        if not data:
            raise HTTPException(status_code=422, detail="Evidence body cannot be empty")
        if len(data) > MAX_EVIDENCE_BYTES:
            raise HTTPException(status_code=413, detail="Evidence exceeds the 4 MB limit")
        try:
            evidence_id = store.save_evidence(scope.family_id, incident_id, data, content_type)
        except KeyError:
            raise HTTPException(status_code=404, detail="Resource not found") from None
        return {"id": evidence_id, "url": f"/api/evidence/{evidence_id}"}

    @app.get("/api/evidence/{evidence_id}")
    def get_evidence(evidence_id: str, scope: FamilyScope = Depends(require_family_scope)) -> FileResponse:
        try:
            path, content_type = store.get_evidence(scope.family_id, evidence_id)
        except (KeyError, FileNotFoundError):
            raise HTTPException(status_code=404, detail="Resource not found") from None
        return FileResponse(path, media_type=content_type, headers={"Cache-Control": "private, no-store"})

    @app.get("/api/devices/{device_id}/commands", response_model=list[DeviceCommand])
    def pending_commands(
        device_id: str,
        after_id: int = Query(default=0, ge=0),
        scope: FamilyScope = Depends(require_family_scope),
    ) -> list[DeviceCommand]:
        try:
            return store.pending_commands(scope.family_id, device_id, after_id)
        except KeyError:
            raise HTTPException(status_code=404, detail="Resource not found") from None

    @app.post("/api/devices/{device_id}/commands/{command_id}/ack", response_model=DeviceCommand)
    def acknowledge_command(
        device_id: str,
        command_id: int,
        scope: FamilyScope = Depends(parent_scope),
    ) -> DeviceCommand:
        require_demo_agent_route()
        try:
            return store.acknowledge_command(scope.family_id, device_id, command_id)
        except KeyError:
            raise HTTPException(status_code=404, detail="Resource not found") from None

    @app.post("/api/devices/{device_id}/telemetry", status_code=status.HTTP_204_NO_CONTENT)
    def record_telemetry(
        device_id: str,
        payload: TelemetryUpdate,
        scope: FamilyScope = Depends(parent_scope),
    ) -> Response:
        require_demo_agent_route()
        try:
            store.record_telemetry(scope.family_id, device_id, payload)
        except KeyError:
            raise HTTPException(status_code=404, detail="Resource not found") from None
        except ValueError:
            raise HTTPException(status_code=404, detail="Resource not found") from None
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    @app.get("/api/daily-report", response_model=DailyReport)
    def daily_report(
        child_id: str = Query(min_length=1, max_length=100),
        report_date: date = Query(default_factory=date.today, alias="date"),
        scope: FamilyScope = Depends(require_family_scope),
    ) -> DailyReport:
        try:
            return store.daily_report(scope.family_id, child_id, report_date)
        except KeyError:
            raise HTTPException(status_code=404, detail="Resource not found") from None

    if (WEB_ROOT / "static").is_dir():
        app.mount("/static", StaticFiles(directory=WEB_ROOT / "static"), name="static")

    def ui() -> FileResponse:
        return FileResponse(WEB_ROOT / "index.html", headers={"Cache-Control": "no-cache"})

    def demo_chat() -> FileResponse:
        return FileResponse(WEB_ROOT / "demo-chat.html", headers={"Cache-Control": "no-cache"})

    app.add_api_route("/", ui, methods=["GET"], include_in_schema=False)
    app.add_api_route("/child", ui, methods=["GET"], include_in_schema=False)
    app.add_api_route("/settings", ui, methods=["GET"], include_in_schema=False)
    app.add_api_route("/incidents/{incident_id}", ui, methods=["GET"], include_in_schema=False)
    app.add_api_route("/demo-chat", demo_chat, methods=["GET"], include_in_schema=False)

    return app


app = create_app()
