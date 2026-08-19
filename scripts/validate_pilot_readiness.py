from __future__ import annotations

import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]


def _load_json(relative_path: str) -> dict[str, Any]:
    return json.loads((ROOT / relative_path).read_text(encoding="utf-8"))


def validate_protocol() -> list[str]:
    errors: list[str] = []
    config_path = ROOT / "config/pilot/protocol.v1.json"
    document_path = ROOT / "docs/pilot/pilot-protocol.md"
    if not config_path.is_file():
        return ["missing pilot protocol configuration"]
    if not document_path.is_file():
        return ["missing pilot protocol document"]

    protocol = _load_json("config/pilot/protocol.v1.json")
    if protocol.get("schema_version") != 1:
        errors.append("pilot protocol schema_version must be 1")
    if protocol.get("pilot_enabled") is not False:
        errors.append("pilot must remain disabled until external entry gates are recorded")
    if protocol.get("initial_mode") != "TECHNICAL_TELEMETRY_AND_SHADOW_ONLY":
        errors.append("pilot must begin with technical telemetry and shadow mode only")

    required_gates = set(protocol.get("required_entry_gates", []))
    for gate in {
        "IDENTITY_AND_TENANT_ISOLATION",
        "RECORDED_LEGAL_AND_PRIVACY_APPROVALS",
        "VERIFIED_FAMILY_DELETION",
        "TRAINED_SUPPORT_ROSTER",
        "ACTIVE_ON_CALL_ROSTER",
    }:
        if gate not in required_gates:
            errors.append(f"pilot protocol is missing entry gate {gate}")

    stops = protocol.get("interruption_conditions", [])
    stop_ids = {item.get("id") for item in stops}
    if stop_ids != {f"PILOT-STOP-{number:02d}" for number in range(1, 6)}:
        errors.append("pilot protocol must define PILOT-STOP-01 through PILOT-STOP-05")
    for stop in stops:
        if not stop.get("action") or not stop.get("restart_requires"):
            errors.append(f"{stop.get('id', 'unknown stop')} needs an action and restart owners")

    document = document_path.read_text(encoding="utf-8")
    for marker in ("Status: rascunho interno", "SHADOW", "SEV0", "rollback", "não comprova"):
        if marker not in document:
            errors.append(f"pilot protocol document is missing marker {marker}")
    return errors


def main() -> int:
    errors = validate_protocol()
    if errors:
        for error in errors:
            print(f"ERROR: {error}")
        return 1
    print("Pilot readiness artifacts are internally consistent; external approvals are not implied.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
