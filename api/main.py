from __future__ import annotations

import sqlite3
from contextlib import asynccontextmanager
from datetime import date
from pathlib import Path

from fastapi import Body, FastAPI, HTTPException, Query, Request, Response, status
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from api.storage import GuardianStore
from guardian_core.config import GuardianSettings
from guardian_core.models import (
    DailyReport,
    Device,
    DeviceCommand,
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
) -> FastAPI:
    runtime_settings = settings or GuardianSettings.from_env()
    db_path = database_path or runtime_settings.database_path
    evidence_path = evidence_directory or runtime_settings.evidence_directory
    store = GuardianStore(db_path, evidence_path)

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        store.initialize()
        yield

    app = FastAPI(
        title="Guardian API",
        version=APP_VERSION,
        description="Local control plane for the Guardian hackathon vertical slice.",
        lifespan=lifespan,
    )
    app.state.store = store
    app.state.settings = runtime_settings

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
            authentication=False,
            tenant_isolation=False,
            production_ready=False,
            notes=[
                "Current observation input is limited to controlled fixtures.",
                "Real macOS observation, OCR, authentication and tenant isolation are not implemented.",
                "The real-enforcement setting is an authorization gate, not proof of an active agent.",
            ],
        )

    @app.post("/api/devices/pair", response_model=Device, status_code=status.HTTP_201_CREATED)
    def pair_device(payload: DevicePairRequest) -> Device:
        if not store.child_exists(payload.child_id):
            raise HTTPException(status_code=404, detail="Child not found")
        return store.pair_device(payload)

    @app.get("/api/devices/{device_id}", response_model=Device)
    def get_device(device_id: str) -> Device:
        try:
            return store.get_device(device_id)
        except KeyError:
            raise HTTPException(status_code=404, detail="Device not found") from None

    @app.get("/api/children/{child_id}/policy", response_model=list[PolicyRule])
    def get_policy(child_id: str) -> list[PolicyRule]:
        if not store.child_exists(child_id):
            raise HTTPException(status_code=404, detail="Child not found")
        return store.get_policy(child_id)

    @app.put("/api/children/{child_id}/policy", response_model=list[PolicyRule])
    def replace_policy(
        child_id: str, rules: list[PolicyRule] = Body(min_length=1, max_length=20)
    ) -> list[PolicyRule]:
        if not store.child_exists(child_id):
            raise HTTPException(status_code=404, detail="Child not found")
        if len({rule.category for rule in rules}) != len(rules):
            raise HTTPException(status_code=422, detail="Policy categories must be unique")
        return store.replace_policy(child_id, rules)

    @app.post("/api/incidents", response_model=Incident, status_code=status.HTTP_201_CREATED)
    def create_incident(payload: IncidentCreate, response: Response) -> Incident:
        if not store.child_exists(payload.child_id):
            raise HTTPException(status_code=404, detail="Child not found")
        if not store.device_exists(payload.device_id):
            raise HTTPException(status_code=404, detail="Device not found")
        try:
            incident, created = store.create_incident(payload)
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
        child_id: str = Query(default="child-demo"),
        limit: int = Query(default=20, ge=1, le=100),
        incident_status: IncidentStatus | None = Query(default=None, alias="status"),
    ) -> list[Incident]:
        if not store.child_exists(child_id):
            raise HTTPException(status_code=404, detail="Child not found")
        return store.list_incidents(child_id, limit, incident_status)

    @app.get("/api/incidents/{incident_id}", response_model=Incident)
    def get_incident(incident_id: str) -> Incident:
        try:
            return store.get_incident(incident_id)
        except KeyError:
            raise HTTPException(status_code=404, detail="Incident not found") from None

    @app.post("/api/incidents/{incident_id}/request-unlock", response_model=Incident)
    def request_unlock(incident_id: str, payload: UnlockRequest) -> Incident:
        try:
            return store.request_unlock(incident_id, payload.explanation)
        except KeyError:
            raise HTTPException(status_code=404, detail="Incident not found") from None
        except ValueError as error:
            raise HTTPException(status_code=409, detail=str(error)) from None

    @app.post("/api/incidents/{incident_id}/unlock", response_model=Incident)
    def unlock(incident_id: str) -> Incident:
        try:
            return store.unlock_incident(incident_id)
        except KeyError:
            raise HTTPException(status_code=404, detail="Incident not found") from None
        except ValueError as error:
            raise HTTPException(status_code=409, detail=str(error)) from None

    @app.post("/api/incidents/{incident_id}/keep-blocked", response_model=Incident)
    def keep_blocked(incident_id: str) -> Incident:
        try:
            return store.keep_blocked(incident_id)
        except KeyError:
            raise HTTPException(status_code=404, detail="Incident not found") from None
        except ValueError as error:
            raise HTTPException(status_code=409, detail=str(error)) from None

    @app.post("/api/incidents/{incident_id}/evidence", status_code=status.HTTP_201_CREATED)
    async def upload_evidence(incident_id: str, request: Request) -> dict[str, str]:
        content_type = request.headers.get("content-type", "").split(";", 1)[0].lower()
        if content_type not in ALLOWED_EVIDENCE_TYPES:
            raise HTTPException(status_code=415, detail="Unsupported evidence type")
        data = await request.body()
        if not data:
            raise HTTPException(status_code=422, detail="Evidence body cannot be empty")
        if len(data) > MAX_EVIDENCE_BYTES:
            raise HTTPException(status_code=413, detail="Evidence exceeds the 4 MB limit")
        try:
            evidence_id = store.save_evidence(incident_id, data, content_type)
        except KeyError:
            raise HTTPException(status_code=404, detail="Incident not found") from None
        return {"id": evidence_id, "url": f"/api/evidence/{evidence_id}"}

    @app.get("/api/evidence/{evidence_id}")
    def get_evidence(evidence_id: str) -> FileResponse:
        try:
            path, content_type = store.get_evidence(evidence_id)
        except (KeyError, FileNotFoundError):
            raise HTTPException(status_code=404, detail="Evidence not found") from None
        return FileResponse(path, media_type=content_type, headers={"Cache-Control": "private, no-store"})

    @app.get("/api/devices/{device_id}/commands", response_model=list[DeviceCommand])
    def pending_commands(device_id: str, after_id: int = Query(default=0, ge=0)) -> list[DeviceCommand]:
        try:
            return store.pending_commands(device_id, after_id)
        except KeyError:
            raise HTTPException(status_code=404, detail="Device not found") from None

    @app.post("/api/devices/{device_id}/commands/{command_id}/ack", response_model=DeviceCommand)
    def acknowledge_command(device_id: str, command_id: int) -> DeviceCommand:
        try:
            return store.acknowledge_command(device_id, command_id)
        except KeyError:
            raise HTTPException(status_code=404, detail="Command not found") from None

    @app.post("/api/devices/{device_id}/telemetry", status_code=status.HTTP_204_NO_CONTENT)
    def record_telemetry(device_id: str, payload: TelemetryUpdate) -> Response:
        try:
            store.record_telemetry(device_id, payload)
        except KeyError:
            raise HTTPException(status_code=404, detail="Device not found") from None
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    @app.get("/api/daily-report", response_model=DailyReport)
    def daily_report(
        child_id: str = Query(default="child-demo"),
        report_date: date = Query(default_factory=date.today, alias="date"),
    ) -> DailyReport:
        try:
            return store.daily_report(child_id, report_date)
        except KeyError:
            raise HTTPException(status_code=404, detail="Child not found") from None

    if (WEB_ROOT / "static").is_dir():
        app.mount("/static", StaticFiles(directory=WEB_ROOT / "static"), name="static")

    def ui() -> FileResponse:
        return FileResponse(WEB_ROOT / "index.html", headers={"Cache-Control": "no-cache"})

    app.add_api_route("/", ui, methods=["GET"], include_in_schema=False)
    app.add_api_route("/child", ui, methods=["GET"], include_in_schema=False)
    app.add_api_route("/settings", ui, methods=["GET"], include_in_schema=False)
    app.add_api_route("/incidents/{incident_id}", ui, methods=["GET"], include_in_schema=False)

    return app


app = create_app()
