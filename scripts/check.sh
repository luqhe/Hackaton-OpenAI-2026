#!/usr/bin/env bash
set -euo pipefail
project_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$project_root"

.venv/bin/python scripts/validate_stage0.py
.venv/bin/python -m ruff check .
.venv/bin/python -m ruff format --check agent api guardian_core risk_engine scripts tests
.venv/bin/python -m pytest
pnpm check:js
pnpm lint:js
pnpm format:check
