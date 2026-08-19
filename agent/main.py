from __future__ import annotations

import argparse
import hashlib
import json
import os
import time
from pathlib import Path

from agent.client import GuardianAPIClient, GuardianAPIError
from agent.enforcer import DemoEnforcer, MacOSEnforcer
from guardian_core.config import GuardianSettings
from guardian_core.gates import apply_runtime_release_gate
from guardian_core.models import IncidentCreate, Observation, PolicyRule, TelemetryUpdate
from guardian_core.policy import apply_policy
from risk_engine import assess_risk

PROJECT_ROOT = Path(__file__).resolve().parents[1]


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
    assessment = assess_risk(observation)
    rules = [PolicyRule.model_validate(item) for item in client.get_policy(args.child_id)]
    decision = apply_policy(assessment, rules)
    decision = apply_runtime_release_gate(decision, settings, fixture_input=True)
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
        poll_commands(client, args.device_id, enforcer, args.poll_interval)
    return 0


def poll_commands(
    client: GuardianAPIClient,
    device_id: str,
    enforcer: DemoEnforcer,
    poll_interval: float,
    once: bool = False,
) -> None:
    last_command_id = 0
    while True:
        enforcer.enforce()
        commands = client.pending_commands(device_id, last_command_id)
        for command in commands:
            if command["type"] == "UNLOCK_APPLICATION":
                enforcer.unblock(command["application"])
                print(f"unlocked={command['application']} command={command['id']}")
            client.acknowledge_command(device_id, command["id"])
            last_command_id = max(last_command_id, command["id"])
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

    poll = subparsers.add_parser("poll", help="Poll and execute pending device commands")
    poll.add_argument("--api-url", default=os.getenv("GUARDIAN_API_URL", "http://127.0.0.1:8000"))
    poll.add_argument("--device-id", default="device-demo")
    poll.add_argument("--state-path", type=Path, default=PROJECT_ROOT / ".data" / "agent-state.json")
    poll.add_argument("--poll-interval", type=float, default=2.0)
    poll.add_argument("--once", action="store_true")
    poll.add_argument("--real-enforcement", action="store_true")

    def handle_poll(args: argparse.Namespace) -> int:
        settings = GuardianSettings.from_env()
        client = GuardianAPIClient(args.api_url)
        enforcer = build_enforcer(args.real_enforcement, args.state_path, settings)
        poll_commands(client, args.device_id, enforcer, args.poll_interval, args.once)
        return 0

    poll.set_defaults(handler=handle_poll)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        return args.handler(args)
    except (GuardianAPIError, OSError, ValueError) as error:
        print(f"Guardian agent error: {error}")
        return 1
    except KeyboardInterrupt:
        print("Guardian agent stopped.")
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
