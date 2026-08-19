from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from guardian_core.models import EnforcementAction, RiskCategory  # noqa: E402
from guardian_core.pilot import PilotKillSwitch, load_pilot_rollout  # noqa: E402
from guardian_core.pilot_control import PilotConfigStore, pilot_config_digest  # noqa: E402


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Validate, activate or roll back Guardian pilot controls")
    parser.add_argument("--state-directory", type=Path, default=Path(".data/pilot-controls"))
    subparsers = parser.add_subparsers(dest="command", required=True)

    validate = subparsers.add_parser("validate")
    validate.add_argument("config", type=Path)

    activate = subparsers.add_parser("activate")
    activate.add_argument("config", type=Path)
    activate.add_argument("--actor-digest", required=True)
    activate.add_argument("--change-reference", required=True)
    activate.add_argument("--expected-active-digest", required=True)

    rollback = subparsers.add_parser("rollback")
    rollback.add_argument("digest")
    rollback.add_argument("--actor-digest", required=True)
    rollback.add_argument("--change-reference", required=True)
    rollback.add_argument("--expected-active-digest", required=True)

    kill_switch = subparsers.add_parser("kill-switch")
    kill_switch.add_argument("--switch-id", required=True)
    kill_switch.add_argument("--ceiling", choices=("LOG", "ALERT"), default="LOG")
    kill_switch.add_argument("--reason", required=True)
    kill_switch.add_argument("--category", choices=tuple(item.value for item in RiskCategory))
    kill_switch.add_argument("--cohort-id")
    kill_switch.add_argument("--actor-digest", required=True)
    kill_switch.add_argument("--change-reference", required=True)
    kill_switch.add_argument("--expected-active-digest", required=True)

    subparsers.add_parser("status")
    return parser


def parse_expected_digest(value: str) -> str | None:
    return None if value.upper() == "NONE" else value


def main() -> int:
    args = build_parser().parse_args()
    store = PilotConfigStore(args.state_directory)
    now = datetime.now(UTC)
    if args.command == "validate":
        config = load_pilot_rollout(args.config)
        print(json.dumps({"valid": True, "digest": pilot_config_digest(config), "mode": config.mode}))
    elif args.command == "activate":
        change = store.activate(
            load_pilot_rollout(args.config),
            actor_subject_digest=args.actor_digest,
            change_reference=args.change_reference,
            changed_at=now,
            expected_active_digest=parse_expected_digest(args.expected_active_digest),
        )
        print(change.model_dump_json())
    elif args.command == "rollback":
        change = store.rollback(
            args.digest,
            actor_subject_digest=args.actor_digest,
            change_reference=args.change_reference,
            changed_at=now,
            expected_active_digest=args.expected_active_digest,
        )
        print(change.model_dump_json())
    elif args.command == "kill-switch":
        change = store.set_kill_switch(
            PilotKillSwitch(
                switch_id=args.switch_id,
                category=RiskCategory(args.category) if args.category else None,
                cohort_id=args.cohort_id,
                ceiling=EnforcementAction(args.ceiling),
                reason=args.reason,
            ),
            actor_subject_digest=args.actor_digest,
            change_reference=args.change_reference,
            changed_at=now,
            expected_active_digest=args.expected_active_digest,
        )
        print(change.model_dump_json())
    else:
        current = store.current()
        print(
            json.dumps(
                {
                    "configured": current is not None,
                    "digest": pilot_config_digest(current) if current else None,
                    "mode": current.mode if current else None,
                }
            )
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
