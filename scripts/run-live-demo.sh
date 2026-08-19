#!/usr/bin/env bash
set -euo pipefail

project_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
python="$project_root/.venv/bin/python"
fixture_launcher="$project_root/scripts/run-demo.sh"
api_url="http://127.0.0.1:8000"
demo_url="$api_url/demo-chat"

if [[ ! -x "$python" ]]; then
  printf 'Ambiente local ausente. Execute bash scripts/bootstrap.sh primeiro.\n' >&2
  exit 1
fi
if [[ ! -r "$fixture_launcher" ]]; then
  printf 'Launcher da fixture ausente: %s\n' "$fixture_launcher" >&2
  exit 1
fi
if ! command -v curl >/dev/null 2>&1; then
  printf 'Dependência local ausente: curl.\n' >&2
  exit 1
fi
if ! command -v open >/dev/null 2>&1; then
  printf 'Dependência local ausente: open.\n' >&2
  exit 1
fi

if ! curl --fail --silent --show-error --max-time 2 "$api_url/api/health" >/dev/null; then
  printf 'API local indisponível em %s. Inicie-a com bash scripts/run-api.sh.\n' "$api_url" >&2
  exit 1
fi
if ! open "$demo_url"; then
  printf 'Não foi possível abrir a conversa local em %s.\n' "$demo_url" >&2
  exit 1
fi

if ! agent_help="$("$python" -m agent.main --help 2>&1)"; then
  printf 'Não foi possível inspecionar o agente local:\n%s\n' "$agent_help" >&2
  exit 1
fi

if [[ "$agent_help" == *"live-demo"* ]]; then
  printf 'mode=OPTIONAL_LIVE_DEMO\n'
  if "$python" -m agent.main live-demo --controlled-demo --wait-for-unlock; then
    exit 0
  else
    live_status=$?
    printf 'live-demo local falhou com status %d; iniciando fallback explícito.\n' \
      "$live_status" >&2
    printf 'source=FIXTURE_FALLBACK\n'
  fi
else
  printf 'live-demo local indisponível; usando a fixture determinística.\n'
  printf 'source=LOCAL_FIXTURE\n'
fi

exec bash "$fixture_launcher"
