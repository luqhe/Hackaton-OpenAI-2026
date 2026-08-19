from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from guardian_core.operations import load_alert_rules  # noqa: E402


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


def validate_support_training() -> list[str]:
    errors: list[str] = []
    config_path = ROOT / "config/pilot/support-training.v1.json"
    curriculum_path = ROOT / "docs/pilot/support-training.md"
    quick_reference_path = ROOT / "docs/pilot/support-quick-reference.md"
    for path in (config_path, curriculum_path, quick_reference_path):
        if not path.is_file():
            errors.append(f"missing support training artifact: {path.relative_to(ROOT)}")
    if errors:
        return errors

    training = _load_json("config/pilot/support-training.v1.json")
    if training.get("schema_version") != 1:
        errors.append("support training schema_version must be 1")
    if training.get("training_complete") is not False:
        errors.append("support training cannot be complete without a real roster")
    if training.get("completions") != []:
        errors.append("support training must not contain fabricated completions")
    if training.get("passing_score_percent", 0) < 85:
        errors.append("support training passing score must be at least 85%")
    if len(training.get("required_modules", [])) != 6:
        errors.append("support training must contain six required modules")
    if len(training.get("must_pass_scenarios", [])) != 5:
        errors.append("support training must contain five must-pass scenarios")

    curriculum = curriculum_path.read_text(encoding="utf-8")
    for module in training.get("required_modules", []):
        if module.split("-", 2)[0] + "-" + module.split("-", 2)[1] not in curriculum:
            errors.append(f"curriculum is missing module {module}")
    for marker in ("não significa que o suporte foi treinado", "SEV0", "kill switch", "85%"):
        if marker not in curriculum:
            errors.append(f"support curriculum is missing marker {marker}")
    return errors


def validate_operational_readiness() -> list[str]:
    errors: list[str] = []
    alerts_path = ROOT / "config/pilot/alerts.v1.json"
    on_call_path = ROOT / "config/pilot/on-call.v1.json"
    operations_path = ROOT / "docs/pilot/operations.md"
    for path in (alerts_path, on_call_path, operations_path):
        if not path.is_file():
            errors.append(f"missing pilot operations artifact: {path.relative_to(ROOT)}")
    if errors:
        return errors

    alerts = _load_json("config/pilot/alerts.v1.json")
    on_call = _load_json("config/pilot/on-call.v1.json")
    if alerts.get("alerts_active") is not False:
        errors.append("alerts cannot be active before an external delivery integration and drill")
    try:
        rules = load_alert_rules(alerts_path)
    except (ValueError, TypeError) as error:
        errors.append(f"invalid pilot alert configuration: {error}")
        rules = []
    expected_metrics = {
        "cross_family_access_events",
        "prohibited_collection_events",
        "api_availability_percent",
        "command_ack_latency_p95_ms",
        "heartbeat_age_max_seconds",
        "offline_queue_depth_max",
        "family_deletion_failures",
    }
    if {rule.metric for rule in rules} != expected_metrics:
        errors.append("pilot alerts do not cover all required operational metrics")
    if on_call.get("roster_active") is not False:
        errors.append("on-call roster cannot be active without real rotations")
    if on_call.get("rotations") != []:
        errors.append("on-call configuration must not contain fabricated rotations")
    if set(on_call.get("required_roles", [])) != {"PRIMARY", "SECONDARY", "SECURITY", "PRIVACY"}:
        errors.append("on-call configuration must require primary, secondary, security and privacy")
    if on_call.get("last_drill_at") is not None or on_call.get("last_drill_result") is not None:
        errors.append("on-call configuration cannot claim an unperformed drill")
    return errors


def validate_telemetry_instrumentation() -> list[str]:
    errors: list[str] = []
    config_path = ROOT / "config/pilot/telemetry.v1.json"
    document_path = ROOT / "docs/pilot/telemetry.md"
    if not config_path.is_file():
        return ["missing pilot telemetry configuration"]
    if not document_path.is_file():
        return ["missing pilot telemetry document"]
    telemetry = _load_json("config/pilot/telemetry.v1.json")
    if telemetry.get("schema_version") != 1:
        errors.append("pilot telemetry schema_version must be 1")
    forbidden = set(telemetry.get("content_fields_forbidden", []))
    if not {"visible_text", "ocr", "screenshot", "transcript", "evidence"}.issubset(forbidden):
        errors.append("pilot telemetry must explicitly forbid observed content fields")
    if len(telemetry.get("onboarding_stages", [])) != 8:
        errors.append("pilot telemetry must define eight onboarding stages")
    command_latency = telemetry.get("command_latency", {})
    if command_latency.get("start") != "device_commands.created_at":
        errors.append("command latency must start at persisted command creation")
    if command_latency.get("end") != "device_commands.acknowledged_at":
        errors.append("command latency must end at persisted agent acknowledgement")
    if command_latency.get("slo_p95_ms") != 5000:
        errors.append("command latency p95 SLO must match the five-second release gate")
    document = document_path.read_text(encoding="utf-8")
    for marker in ("R5-05", "null", "p50", "p95", "não comprova consentimento"):
        if marker not in document:
            errors.append(f"pilot telemetry document is missing marker {marker}")
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
    training = _load_json("config/pilot/support-training.v1.json")
    if training.get("training_complete") is not True:
        blockers.append("support training roster is not complete")
    alerts = _load_json("config/pilot/alerts.v1.json")
    on_call = _load_json("config/pilot/on-call.v1.json")
    if alerts.get("alerts_active") is not True:
        blockers.append("operational alert delivery is not active")
    if on_call.get("roster_active") is not True:
        blockers.append("on-call roster and drill are not active")
    return blockers


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--activation-gate",
        action="store_true",
        help="fail unless all external approvals and pilot enablement are recorded",
    )
    args = parser.parse_args()
    errors = (
        validate_protocol()
        + validate_legal_package()
        + validate_support_training()
        + validate_operational_readiness()
        + validate_telemetry_instrumentation()
    )
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
