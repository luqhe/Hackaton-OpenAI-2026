from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

PRODUCT_AND_SECURITY_FILES = {
    "docs/product/release-gates.md": tuple(f"R0-{number:02d}" for number in range(1, 7)),
    "docs/security/threat-model.md": ("R0-07", "R0-09", "R0-10", "R0-11"),
    "docs/security/risk-register.md": ("R0-12",),
    "docs/privacy/data-map.md": ("R0-08",),
    "docs/security/response-playbooks.md": ("Playbook A", "Playbook B", "Playbook C", "Playbook D"),
}

ENGINEERING_FILES = {
    "docs/engineering/api-versioning-and-migrations.md": ("R0-15", "X-Guardian-API-Version"),
    "docs/engineering/environments.md": ("R0-17", "development", "staging", "production"),
    "docs/adr/0001-native-swift-helper-python-agent.md": ("Status: Accepted", "## Decision"),
    "docs/adr/0002-modular-fastapi-monolith.md": ("Status: Accepted", "## Decision"),
    "docs/adr/0003-data-and-evidence-storage.md": ("Status: Accepted", "## Decision"),
    "docs/adr/0004-device-command-protocol.md": ("Status: Accepted", "## Decision"),
}

QUALITY_FILES = {
    ".github/workflows/ci.yml": (
        "python -m pytest",
        "python -m ruff check .",
        "python -m ruff format --check agent api guardian_core risk_engine scripts tests",
        "pnpm lint:js",
        "pnpm format:check",
        "scripts/validate_stage0.py",
    ),
    "package.json": ("lint:js", "format:check", "eslint", "prettier"),
    "pyproject.toml": ("[tool.ruff]", "[tool.ruff.lint]", "[tool.ruff.format]"),
}


def validate_files(required: dict[str, tuple[str, ...]]) -> list[str]:
    errors: list[str] = []
    for relative_path, markers in required.items():
        path = ROOT / relative_path
        if not path.is_file():
            errors.append(f"missing required file: {relative_path}")
            continue
        content = path.read_text(encoding="utf-8")
        for marker in markers:
            if marker not in content:
                errors.append(f"{relative_path} is missing marker {marker}")
    return errors


def validate_product_and_security() -> list[str]:
    errors = validate_files(PRODUCT_AND_SECURITY_FILES)
    gates = (ROOT / "docs/product/release-gates.md").read_text(encoding="utf-8")
    for action in ("IGNORE", "LOG", "ALERT", "BLOCK"):
        if f"`{action}`" not in gates:
            errors.append(f"release gates do not define {action}")

    threat_model = (ROOT / "docs/security/threat-model.md").read_text(encoding="utf-8")
    threat_ids = {int(value) for value in re.findall(r"T-(\d{2})", threat_model)}
    if not set(range(1, 15)).issubset(threat_ids):
        errors.append("threat model must include T-01 through T-14")

    risk_register = (ROOT / "docs/security/risk-register.md").read_text(encoding="utf-8")
    risk_ids = {int(value) for value in re.findall(r"RISK-(\d{3})", risk_register)}
    if len(risk_ids) < 12:
        errors.append("risk register must contain at least 12 unique risks")
    return errors


def validate_engineering() -> list[str]:
    errors = validate_files(ENGINEERING_FILES)
    for relative_path in ENGINEERING_FILES:
        if not relative_path.startswith("docs/adr/"):
            continue
        content = (ROOT / relative_path).read_text(encoding="utf-8")
        for heading in ("## Context", "## Decision", "## Consequences"):
            if heading not in content:
                errors.append(f"{relative_path} is missing ADR heading {heading}")
    return errors


def validate_quality_pipeline() -> list[str]:
    return validate_files(QUALITY_FILES)


def validate_roadmap_status() -> list[str]:
    roadmap = (ROOT / "ROADMAP.md").read_text(encoding="utf-8")
    errors: list[str] = []
    for number in range(1, 19):
        marker = f"- [x] `R0-{number:02d}`"
        if marker not in roadmap:
            errors.append(f"ROADMAP.md has not marked R0-{number:02d} as implemented")
    if "branch protection no GitHub" not in roadmap:
        errors.append("ROADMAP.md must keep the external branch-protection gate visible")
    return errors


def main() -> int:
    errors = (
        validate_product_and_security()
        + validate_engineering()
        + validate_quality_pipeline()
        + validate_roadmap_status()
    )
    if errors:
        for error in errors:
            print(f"ERROR: {error}")
        return 1
    print("Stage 0 documentation is valid.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
