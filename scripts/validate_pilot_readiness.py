from __future__ import annotations

import argparse
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


def validate_legal_package() -> list[str]:
    errors: list[str] = []
    approval_path = ROOT / "config/pilot/legal-approvals.v1.json"
    if not approval_path.is_file():
        return ["missing legal approval record"]
    approvals = _load_json("config/pilot/legal-approvals.v1.json")
    if approvals.get("schema_version") != 1:
        errors.append("legal approval schema_version must be 1")
    if approvals.get("approved_for_pilot") is not False:
        errors.append("draft legal package must not claim pilot approval")

    expected_reviewers = {"LEGAL", "PRIVACY", "PRODUCT_SAFETY"}
    records = approvals.get("required_approvals", {})
    if set(records) != expected_reviewers:
        errors.append("legal approval record must require Legal, Privacy and Product Safety")
    for role, record in records.items():
        if record.get("status") != "PENDING":
            errors.append(f"{role} must remain PENDING until a real review is recorded")
        if any(record.get(field) is not None for field in ("reviewer", "reviewed_at", "scope")):
            errors.append(f"{role} cannot have fabricated review metadata")

    documents = approvals.get("documents", [])
    if len(documents) != 4:
        errors.append("legal package must list four controlled documents")
    for relative_path in documents:
        path = ROOT / relative_path
        if not path.is_file():
            errors.append(f"missing legal package document: {relative_path}")
            continue
        content = path.read_text(encoding="utf-8")
        if "R5-02" not in content:
            errors.append(f"{relative_path} is missing the R5-02 marker")

    consent = ROOT / "docs/pilot/legal/consent-and-assent.md"
    if consent.is_file():
        content = consent.read_text(encoding="utf-8")
        for marker in ("voluntário", "retirar", "não coleta câmera ou microfone", "não aprovada"):
            if marker not in content:
                errors.append(f"consent draft is missing marker {marker}")
    return errors


def activation_blockers() -> list[str]:
    blockers: list[str] = []
    protocol = _load_json("config/pilot/protocol.v1.json")
    approvals = _load_json("config/pilot/legal-approvals.v1.json")
    if protocol.get("pilot_enabled") is not True:
        blockers.append("pilot protocol is disabled")
    if approvals.get("approved_for_pilot") is not True:
        blockers.append("legal/privacy/product-safety approval is not recorded")
    for role, record in approvals.get("required_approvals", {}).items():
        if record.get("status") != "APPROVED":
            blockers.append(f"{role} approval is {record.get('status', 'MISSING')}")
    return blockers


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--activation-gate",
        action="store_true",
        help="fail unless all external approvals and pilot enablement are recorded",
    )
    args = parser.parse_args()
    errors = validate_protocol() + validate_legal_package()
    if errors:
        for error in errors:
            print(f"ERROR: {error}")
        return 1
    if args.activation_gate:
        blockers = activation_blockers()
        if blockers:
            for blocker in blockers:
                print(f"BLOCKED: {blocker}")
            return 2
        print("Pilot activation gate passed.")
        return 0
    print("Pilot readiness artifacts are internally consistent; external approvals are not implied.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
