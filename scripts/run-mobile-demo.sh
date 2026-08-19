#!/usr/bin/env bash
set -euo pipefail

project_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$project_root"

if [[ ! -x .venv/bin/python ]]; then
  printf 'Ambiente ausente. Execute bash scripts/bootstrap.sh primeiro.\n' >&2
  exit 1
fi

export GUARDIAN_DEMO_MODE=true
export GUARDIAN_ENVIRONMENT=development
export GUARDIAN_API_URL=http://127.0.0.1:8000

exec .venv/bin/python -m agent.main demo --api-url "$GUARDIAN_API_URL" --child-id child-demo --device-id device-demo --wait-for-unlock
