#!/usr/bin/env bash
set -euo pipefail
project_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
data_root="$project_root/.data"

if [[ "$(dirname "$data_root")" != "$project_root" || "$(basename "$data_root")" != ".data" ]]; then
  printf 'Caminho de dados inesperado; reset cancelado.\n' >&2
  exit 1
fi
rm -rf -- "$data_root"
printf 'Dados locais da demo removidos. A API recriará o banco inicial no próximo início.\n'

