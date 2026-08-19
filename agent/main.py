from __future__ import annotations

import argparse
import hashlib
import json
import os
import time
from collections.abc import Sequence
from pathlib import Path

from agent.client import GuardianAPIClient, GuardianAPIError
from agent.context import ObservationContextBuffer
from agent.diagnostics import PerformanceMonitor
from agent.enforcer import DemoEnforcer, MacOSEnforcer
from agent.evidence import EphemeralCapture, build_minimal_png
from agent.observer import MacOSObserver, ObserverPermissionError
from agent.outbox import OutboxItem, PersistentOutbox
from agent.scheduler import AdaptiveObservationSchedule, SuspensionDetector
from agent.state import AgentStateStore
from agent.structured_log import StructuredAgentLogger
from guardian_core.config import Environment, GuardianSettings
from guardian_core.gates import apply_runtime_release_gate
from guardian_core.models import (
    DeviceHeartbeat,
    IncidentCreate,
    Observation,
    PolicyDecision,
    PolicyRule,
    RiskAssessment,
    TelemetryUpdate,
)
from guardian_core.policy import apply_policy
from guardian_core.version import APP_VERSION
from risk_engine import assess_risk
from risk_engine.context import build_context
from risk_engine.contracts import ContextBundle, ProviderDescriptor
from risk_engine.openai import (
    DEFAULT_MODEL,
    OPENAI_PROMPT_VERSION,
    OPENAI_PROVIDER_VERSION,
    OpenAIRiskError,
    assess_screenshot,
)
from risk_engine.pipeline import AnalysisSource, ContextualRiskPipeline

PROJECT_ROOT = Path(__file__).resolve().parents[1]
AGENT_LOGGER = StructuredAgentLogger()


def apply_validated_policy(
    raw_assessment: object,
    *,
    client: GuardianAPIClient,
    child_id: str,
    settings: GuardianSettings,
    fixture_input: bool,
) -> tuple[RiskAssessment, PolicyDecision]:
    """Validate classifier output before reading or applying any family rule."""
    assessment = RiskAssessment.model_validate(raw_assessment)
    rules = [PolicyRule.model_validate(item) for item in client.get_policy(child_id)]
    decision = apply_policy(assessment, rules)
    decision = apply_runtime_release_gate(decision, settings, fixture_input=fixture_input)
    return assessment, decision


def reject_invalid_pipeline_output(errors: tuple[str, ...]) -> None:
    invalid_errors = {"ProviderInvalidOutputError", "OpenAIInvalidRiskError"}
    if invalid_errors.intersection(errors):
        raise ValueError(
            "Invalid classifier assessment: unexpected or incomplete fields, including action, "
            "are rejected before policy evaluation"
        )


def flush_offline_outbox(outbox: PersistentOutbox, client: GuardianAPIClient) -> int:
    def deliver(item: OutboxItem) -> bool:
        try:
            if item.kind == "TELEMETRY":
                client.record_telemetry(item.device_id, item.payload)
            else:
                client.create_incident(item.payload)
        except GuardianAPIError:
            return False
        return True

    return outbox.flush(deliver)


def record_telemetry_or_queue(
    client: GuardianAPIClient,
    outbox: PersistentOutbox,
    device_id: str,
    payload: dict[str, object],
) -> None:
    try:
        client.record_telemetry(device_id, payload)
    except GuardianAPIError:
        item = outbox.enqueue("TELEMETRY", device_id, payload)
        AGENT_LOGGER.event("offline_queue_added", kind="TELEMETRY", item_id=item.id)
        print(f"offline_queue=TELEMETRY id={item.id}")


def create_incident_or_queue(
    client: GuardianAPIClient,
    outbox: PersistentOutbox,
    device_id: str,
    payload: dict[str, object],
) -> dict[str, object] | None:
    try:
        return client.create_incident(payload)
    except GuardianAPIError:
        item = outbox.enqueue("INCIDENT", device_id, payload)
        AGENT_LOGGER.event("offline_queue_added", kind="INCIDENT", item_id=item.id)
        print(f"offline_queue=INCIDENT id={item.id}")
        return None


def runtime_state_store_for(args: argparse.Namespace) -> AgentStateStore:
    default_path = args.state_path.with_name("runtime-state.json")
    return AgentStateStore(getattr(args, "runtime_state_path", default_path))


class LiveScreenshotProvider:
    """Adapter keeps the live entrypoint injectable while using the R3 pipeline."""

    descriptor = ProviderDescriptor(
        provider="openai",
        provider_version=OPENAI_PROVIDER_VERSION,
        model_version=DEFAULT_MODEL,
        prompt_version=OPENAI_PROMPT_VERSION,
    )

    def classify(self, context: ContextBundle, *, timeout: float) -> RiskAssessment:
        if context.selected_frame_path is None:
            raise OpenAIRiskError("A selected PNG frame is required for live analysis")
        return assess_screenshot(
            context.selected_frame_path,
            context.observation,
            timeout=timeout,
        )


def load_fixture(path: Path) -> tuple[Observation, str]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    observation = Observation(
        app_name=payload["app_name"],
        window_title=payload.get("window_title", ""),
        visible_text=payload.get("visible_text", ""),
        media_detected=payload.get("media_detected", False),
        recent_messages=payload.get("messages", []),
    )
    transcript = "\n".join(f"{message.speaker}: {message.text}" for message in observation.recent_messages)
    return observation, transcript


def build_enforcer(
    real_enforcement: bool,
    state_path: Path,
    settings: GuardianSettings,
) -> DemoEnforcer:
    if not real_enforcement:
        return DemoEnforcer(state_path)
    if not settings.real_enforcement_enabled:
        raise ValueError(
            "Real enforcement requires GUARDIAN_REAL_ENFORCEMENT_ENABLED=true in addition to the CLI flag"
        )
    allowed = {
        item.strip()
        for item in os.getenv("GUARDIAN_BLOCKABLE_APPS", "Guardian Demo Chat").split(",")
        if item.strip()
    }
    return MacOSEnforcer(state_path, allowed)


def run_fixture(args: argparse.Namespace) -> int:
    settings = GuardianSettings.from_env()
    client = GuardianAPIClient(args.api_url)
    observation, transcript = load_fixture(args.fixture)
    assessment, decision = apply_validated_policy(
        assess_risk(observation),
        client=client,
        child_id=args.child_id,
        settings=settings,
        fixture_input=True,
    )
    print(
        f"assessment={assessment.risk} category={assessment.category} confidence={assessment.confidence:.2f}"
    )
    print(f"decision={decision.action} reason={decision.reason}")

    client.record_telemetry(
        args.device_id,
        TelemetryUpdate(
            child_id=args.child_id,
            screen_changes=1,
            suspicious_events=1 if assessment.risk != "SAFE" else 0,
            app_name=observation.app_name,
            session_seconds=args.session_seconds,
        ).model_dump(mode="json"),
    )
    if decision.action == "IGNORE":
        print("No incident created.")
        return 0

    enforcer = build_enforcer(args.real_enforcement, args.state_path, settings)
    deduplication_key = hashlib.sha256(
        f"{args.device_id}|{observation.app_name}|{transcript}".encode()
    ).hexdigest()
    incident_payload = IncidentCreate(
        child_id=args.child_id,
        device_id=args.device_id,
        application=observation.app_name,
        occurred_at=observation.timestamp,
        assessment=assessment,
        decision=decision,
        deduplication_key=deduplication_key,
    )
    incident = client.create_incident(incident_payload.model_dump(mode="json"))
    if decision.action == "BLOCK":
        enforcer.block(observation.app_name)
    if transcript:
        client.upload_text_evidence(incident["id"], transcript)
    print(f"incident={incident['id']} status={incident['status']}")
    print(f"parent_view={args.api_url}/incidents/{incident['id']}")
    print(f"child_view={args.api_url}/child?incident={incident['id']}")

    if args.wait_for_unlock:
        print("Waiting for a parent decision. Press Ctrl+C to stop.")
        poll_commands(
            client,
            args.device_id,
            enforcer,
            args.poll_interval,
            state_store=runtime_state_store_for(args),
        )
    return 0


def run_live_demo(args: argparse.Namespace) -> int:
    settings = GuardianSettings.from_env()
    if not args.controlled_demo:
        raise ValueError("live-demo requires --controlled-demo")
    if settings.environment != Environment.DEVELOPMENT:
        raise ValueError("--controlled-demo is available only in development")
    if args.countdown < 0:
        raise ValueError("--countdown cannot be negative")

    client = GuardianAPIClient(args.api_url)
    observer = MacOSObserver()
    temporary_capture = EphemeralCapture.create()
    screenshot_path = temporary_capture.path

    try:
        for remaining in range(args.countdown, 0, -1):
            print(f"capture_in={remaining}")
            time.sleep(1)
        observer.capture_screen(screenshot_path)
        application = observer.get_active_application()
        _, screen_hash = observer.detect_change(screenshot_path)
        observation = Observation(app_name=application, screen_hash=screen_hash)
        context = build_context(observation, selected_frame_path=screenshot_path)
        pipeline_result = ContextualRiskPipeline(
            remote_provider=LiveScreenshotProvider(),
            timeout_seconds=args.openai_timeout,
        ).assess(context)
        reject_invalid_pipeline_output(pipeline_result.errors)
        assessment, decision = apply_validated_policy(
            pipeline_result.assessment,
            client=client,
            child_id=args.child_id,
            settings=settings,
            fixture_input=args.controlled_demo,
        )
        source = "OPENAI" if pipeline_result.source == AnalysisSource.REMOTE else pipeline_result.source.value
        print(
            f"source={source} risk={assessment.risk} category={assessment.category} "
            f"confidence={assessment.confidence:.2f}"
        )
        if pipeline_result.errors:
            print(f"analysis_fallback={','.join(pipeline_result.errors)} automatic_block=false")
        print(f"decision={decision.action} reason={decision.reason}")

        client.record_telemetry(
            args.device_id,
            TelemetryUpdate(
                child_id=args.child_id,
                screen_changes=1,
                suspicious_events=1 if assessment.risk != "SAFE" else 0,
                app_name=observation.app_name,
            ).model_dump(mode="json"),
        )
        if decision.action == "IGNORE":
            print("No incident created.")
            return 0

        enforcer = build_enforcer(args.real_enforcement, args.state_path, settings)
        incident_payload = IncidentCreate(
            child_id=args.child_id,
            device_id=args.device_id,
            application=observation.app_name,
            occurred_at=observation.timestamp,
            assessment=assessment,
            decision=decision,
            deduplication_key=hashlib.sha256(
                f"{args.device_id}|{observation.app_name}|{screen_hash}".encode()
            ).hexdigest(),
        )
        incident = client.create_incident(incident_payload.model_dump(mode="json"))
        client.upload_png_evidence(incident["id"], build_minimal_png(screenshot_path))
        if decision.action == "BLOCK":
            enforcer.block(observation.app_name)
        temporary_capture.delete()

        print(f"incident={incident['id']} status={incident['status']}")
        print(f"parent_view={args.api_url}/incidents/{incident['id']}")
        print(f"child_view={args.api_url}/child?incident={incident['id']}")
        if args.wait_for_unlock:
            print("Waiting for a parent decision. Press Ctrl+C to stop.")
            poll_commands(
                client,
                args.device_id,
                enforcer,
                args.poll_interval,
                state_store=runtime_state_store_for(args),
            )
        return 0
    finally:
        temporary_capture.delete()


def run_observer(args: argparse.Namespace) -> int:
    """Run the adaptive real-screen observation loop on macOS."""
    settings = GuardianSettings.from_env()
    client = GuardianAPIClient(args.api_url)
    state_store = AgentStateStore(args.runtime_state_path)
    outbox = PersistentOutbox(args.outbox_path)
    runtime_state = state_store.load()
    observer = MacOSObserver(
        change_threshold=args.change_threshold,
        initial_hash=runtime_state.last_screen_hash,
    )
    enforcer = build_enforcer(args.real_enforcement, args.state_path, settings)
    context = ObservationContextBuffer()
    schedule = AdaptiveObservationSchedule(
        minimum_seconds=args.minimum_interval,
        maximum_seconds=args.maximum_interval,
        backoff_factor=args.backoff_factor,
    )
    suspension_detector = SuspensionDetector()
    cycle = 0

    while args.max_cycles == 0 or cycle < args.max_cycles:
        if suspension_detector.check(expected_interval=schedule.current_seconds):
            observer.reset_after_wake()
            schedule.report_wake()
            AGENT_LOGGER.event("system_wake_detected")
        cycle += 1
        delivered = flush_offline_outbox(outbox, client)
        if delivered:
            print(f"offline_queue_flushed={delivered}")
        with EphemeralCapture.create() as capture:
            captured = observer.capture_if_changed(capture.path)
            if captured is None:
                next_interval = schedule.report_observation(changed=False)
                print(f"observation=STATIC next_in={next_interval:.1f}")
            else:
                screenshot_path, screen_hash = captured
                runtime_state = runtime_state.update(
                    session_id=args.session_id,
                    last_screen_hash=screen_hash,
                )
                state_store.save(runtime_state)
                application = observer.get_active_application()
                client.record_heartbeat(
                    args.device_id,
                    DeviceHeartbeat(
                        agent_version=APP_VERSION,
                        screen_recording_permission=True,
                        accessibility_permission=True,
                        observer_healthy=True,
                        offline_queue_depth=len(outbox.items()),
                    ).model_dump(mode="json"),
                )
                observation = Observation(app_name=application, screen_hash=screen_hash)
                context.add(observation, session_id=args.session_id)
                risk_context = build_context(
                    observation,
                    selected_frame_path=screenshot_path,
                )
                pipeline_result = ContextualRiskPipeline(
                    remote_provider=LiveScreenshotProvider(),
                    timeout_seconds=args.openai_timeout,
                ).assess(risk_context)
                reject_invalid_pipeline_output(pipeline_result.errors)
                assessment, decision = apply_validated_policy(
                    pipeline_result.assessment,
                    client=client,
                    child_id=args.child_id,
                    settings=settings,
                    fixture_input=False,
                )
                telemetry = TelemetryUpdate(
                    child_id=args.child_id,
                    screen_changes=1,
                    suspicious_events=1 if assessment.risk != "SAFE" else 0,
                    app_name=application,
                ).model_dump(mode="json")
                record_telemetry_or_queue(
                    client,
                    outbox,
                    args.device_id,
                    telemetry,
                )
                source = (
                    "OPENAI"
                    if pipeline_result.source == AnalysisSource.REMOTE
                    else pipeline_result.source.value
                )
                print(
                    f"source={source} risk={assessment.risk} category={assessment.category} "
                    f"confidence={assessment.confidence:.2f} decision={decision.action}"
                )
                if pipeline_result.errors:
                    print(f"analysis_fallback={','.join(pipeline_result.errors)} automatic_block=false")
                AGENT_LOGGER.event(
                    "observation_assessed",
                    risk=assessment.risk,
                    category=assessment.category,
                    decision=decision.action,
                    application=application,
                )
                if decision.action != "IGNORE":
                    incident_payload = IncidentCreate(
                        child_id=args.child_id,
                        device_id=args.device_id,
                        application=application,
                        occurred_at=observation.timestamp,
                        assessment=assessment,
                        decision=decision,
                        deduplication_key=hashlib.sha256(
                            f"{args.device_id}|{application}|{screen_hash}".encode()
                        ).hexdigest(),
                    ).model_dump(mode="json")
                    incident = create_incident_or_queue(
                        client,
                        outbox,
                        args.device_id,
                        incident_payload,
                    )
                    if incident is not None:
                        client.upload_png_evidence(str(incident["id"]), build_minimal_png(screenshot_path))
                    if decision.action == "BLOCK":
                        enforcer.block(application)
                    if incident is not None:
                        print(f"incident={incident['id']} status={incident['status']}")
                next_interval = schedule.report_observation(changed=True)

        if args.max_cycles and cycle >= args.max_cycles:
            return 0
        time.sleep(next_interval)

    return 0


def run_diagnostics(args: argparse.Namespace) -> int:
    if args.samples <= 0:
        raise ValueError("samples must be positive")
    if args.interval < 0:
        raise ValueError("interval cannot be negative")
    monitor = PerformanceMonitor(args.data_directory)
    for index in range(args.samples):
        snapshot = monitor.sample()
        print(json.dumps(snapshot.as_json_dict(), sort_keys=True, separators=(",", ":")))
        if index + 1 < args.samples:
            time.sleep(args.interval)
    return 0


def poll_commands(
    client: GuardianAPIClient,
    device_id: str,
    enforcer: DemoEnforcer,
    poll_interval: float,
    once: bool = False,
    state_store: AgentStateStore | None = None,
) -> None:
    runtime_state = state_store.load() if state_store is not None else None
    last_command_id = runtime_state.last_command_id if runtime_state is not None else 0
    while True:
        enforcer.enforce()
        commands = client.pending_commands(device_id, last_command_id)
        for command in commands:
            if command["type"] == "UNLOCK_APPLICATION":
                enforcer.unblock(command["application"])
                print(f"unlocked={command['application']} command={command['id']}")
            client.acknowledge_command(device_id, command["id"])
            last_command_id = max(last_command_id, command["id"])
            if state_store is not None and runtime_state is not None:
                runtime_state = runtime_state.update(last_command_id=last_command_id)
                state_store.save(runtime_state)
        if once:
            return
        time.sleep(poll_interval)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Guardian edge agent")
    subparsers = parser.add_subparsers(dest="command", required=True)

    demo = subparsers.add_parser("demo", help="Run one reproducible fixture through the full pipeline")
    demo.add_argument(
        "--fixture",
        type=Path,
        default=PROJECT_ROOT / "fixtures" / "dangerous_contact" / "session.json",
    )
    demo.add_argument("--api-url", default=os.getenv("GUARDIAN_API_URL", "http://127.0.0.1:8000"))
    demo.add_argument("--child-id", default="child-demo")
    demo.add_argument("--device-id", default="device-demo")
    demo.add_argument("--session-seconds", type=int, default=348)
    demo.add_argument("--state-path", type=Path, default=PROJECT_ROOT / ".data" / "agent-state.json")
    demo.add_argument("--wait-for-unlock", action="store_true")
    demo.add_argument("--poll-interval", type=float, default=2.0)
    demo.add_argument(
        "--real-enforcement",
        action="store_true",
        help="Actually quit an allow-listed macOS demo app. Never enabled by default.",
    )
    demo.set_defaults(handler=run_fixture)

    live_demo = subparsers.add_parser(
        "live-demo",
        help="Capture one real macOS screenshot and assess it with OpenAI",
    )
    live_demo.add_argument(
        "--controlled-demo",
        action="store_true",
        help="Confirm synthetic demo content; accepted only in development",
    )
    live_demo.add_argument(
        "--api-url",
        default=os.getenv("GUARDIAN_API_URL", "http://127.0.0.1:8000"),
    )
    live_demo.add_argument("--child-id", default="child-demo")
    live_demo.add_argument("--device-id", default="device-demo")
    live_demo.add_argument("--state-path", type=Path, default=PROJECT_ROOT / ".data" / "agent-state.json")
    live_demo.add_argument("--countdown", type=int, default=3)
    live_demo.add_argument("--openai-timeout", type=float, default=20)
    live_demo.add_argument("--wait-for-unlock", action="store_true")
    live_demo.add_argument("--poll-interval", type=float, default=2.0)
    live_demo.add_argument("--real-enforcement", action="store_true")
    live_demo.set_defaults(handler=run_live_demo)

    observe = subparsers.add_parser(
        "observe",
        help="Continuously observe meaningful macOS screen changes",
    )
    observe.add_argument("--api-url", default=os.getenv("GUARDIAN_API_URL", "http://127.0.0.1:8000"))
    observe.add_argument("--child-id", default="child-demo")
    observe.add_argument("--device-id", default="device-demo")
    observe.add_argument("--session-id", default="interactive")
    observe.add_argument("--state-path", type=Path, default=PROJECT_ROOT / ".data" / "agent-state.json")
    observe.add_argument(
        "--runtime-state-path",
        type=Path,
        default=PROJECT_ROOT / ".data" / "runtime-state.json",
    )
    observe.add_argument(
        "--outbox-path",
        type=Path,
        default=PROJECT_ROOT / ".data" / "outbox.json",
    )
    observe.add_argument("--openai-timeout", type=float, default=20)
    observe.add_argument("--minimum-interval", type=float, default=10)
    observe.add_argument("--maximum-interval", type=float, default=60)
    observe.add_argument("--backoff-factor", type=float, default=1.5)
    observe.add_argument("--change-threshold", type=int, default=8)
    observe.add_argument(
        "--max-cycles",
        type=int,
        default=0,
        help="Stop after N capture cycles; zero keeps observing",
    )
    observe.add_argument("--real-enforcement", action="store_true")
    observe.set_defaults(handler=run_observer)

    diagnostics = subparsers.add_parser(
        "diagnostics",
        help="Measure CPU, memory, battery, disk and network counters",
    )
    diagnostics.add_argument(
        "--data-directory",
        type=Path,
        default=PROJECT_ROOT / ".data",
    )
    diagnostics.add_argument("--samples", type=int, default=6)
    diagnostics.add_argument("--interval", type=float, default=10)
    diagnostics.set_defaults(handler=run_diagnostics)

    poll = subparsers.add_parser("poll", help="Poll and execute pending device commands")
    poll.add_argument("--api-url", default=os.getenv("GUARDIAN_API_URL", "http://127.0.0.1:8000"))
    poll.add_argument("--device-id", default="device-demo")
    poll.add_argument("--state-path", type=Path, default=PROJECT_ROOT / ".data" / "agent-state.json")
    poll.add_argument(
        "--runtime-state-path",
        type=Path,
        default=PROJECT_ROOT / ".data" / "runtime-state.json",
    )
    poll.add_argument("--poll-interval", type=float, default=2.0)
    poll.add_argument("--once", action="store_true")
    poll.add_argument("--real-enforcement", action="store_true")

    def handle_poll(args: argparse.Namespace) -> int:
        settings = GuardianSettings.from_env()
        client = GuardianAPIClient(args.api_url)
        enforcer = build_enforcer(args.real_enforcement, args.state_path, settings)
        poll_commands(
            client,
            args.device_id,
            enforcer,
            args.poll_interval,
            args.once,
            state_store=runtime_state_store_for(args),
        )
        return 0

    poll.set_defaults(handler=handle_poll)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args.handler(args)
    except (GuardianAPIError, ObserverPermissionError, OpenAIRiskError, OSError, ValueError) as error:
        AGENT_LOGGER.event("agent_error", level="ERROR", error_type=type(error).__name__)
        print(f"Guardian agent error: {error}")
        return 1
    except KeyboardInterrupt:
        print("Guardian agent stopped.")
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
