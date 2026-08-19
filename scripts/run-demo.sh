#!/usr/bin/env bash
set -euo pipefail
project_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$project_root"

if [[ ! -x .venv/bin/python ]]; then
  printf 'Ambiente ausente. Execute ./scripts/bootstrap.sh primeiro.\n' >&2
  exit 1
fi
.venv/bin/python -m agent.main demo --wait-for-unlock
