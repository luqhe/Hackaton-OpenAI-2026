from scripts.validate_pilot_readiness import (
    activation_blockers,
    validate_family_deletion,
    validate_legal_package,
    validate_operational_readiness,
    validate_protocol,
    validate_support_training,
    validate_telemetry_instrumentation,
)


def test_pilot_protocol_is_safe_and_complete() -> None:
    assert validate_protocol() == []


def test_legal_package_is_complete_without_claiming_external_approval() -> None:
    assert validate_legal_package() == []


def test_activation_gate_stays_closed_until_real_approvals_are_recorded() -> None:
    blockers = activation_blockers()
    assert "pilot protocol is disabled" in blockers
    assert "legal/privacy/product-safety approval is not recorded" in blockers
    pending_roles = {
        item.split(" approval", 1)[0] for item in blockers if item.endswith(" approval is PENDING")
    }
    assert pending_roles == {
        "LEGAL",
        "PRIVACY",
        "PRODUCT_SAFETY",
    }
    assert "support training roster is not complete" in blockers
    assert "operational alert delivery is not active" in blockers
    assert "on-call roster and drill are not active" in blockers
    assert "family deletion does not cover pilot external stores" in blockers


def test_support_training_is_complete_but_roster_is_honestly_pending() -> None:
    assert validate_support_training() == []


def test_operational_rules_are_valid_without_claiming_live_paging() -> None:
    assert validate_operational_readiness() == []


def test_pilot_telemetry_is_minimized_and_matches_command_slo() -> None:
    assert validate_telemetry_instrumentation() == []


def test_family_deletion_proof_keeps_external_stores_out_of_scope() -> None:
    assert validate_family_deletion() == []
