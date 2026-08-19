from scripts.validate_stage0 import (
    validate_engineering,
    validate_product_and_security,
    validate_quality_pipeline,
    validate_roadmap_status,
)


def test_product_and_security_stage0_artifacts_are_complete() -> None:
    assert validate_product_and_security() == []


def test_engineering_stage0_artifacts_are_complete() -> None:
    assert validate_engineering() == []


def test_quality_pipeline_runs_all_required_checks() -> None:
    assert validate_quality_pipeline() == []


def test_roadmap_marks_implemented_stage0_work_and_keeps_external_gates_open() -> None:
    assert validate_roadmap_status() == []
