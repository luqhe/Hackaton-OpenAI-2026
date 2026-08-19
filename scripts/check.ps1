$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $projectRoot

& ".\.venv\Scripts\python.exe" scripts\validate_stage0.py
& ".\.venv\Scripts\python.exe" -m ruff check .
& ".\.venv\Scripts\python.exe" -m ruff format --check agent api guardian_core risk_engine scripts tests
& ".\.venv\Scripts\python.exe" -m pytest

$pnpm = Get-Command pnpm -ErrorAction SilentlyContinue
if (-not $pnpm) {
    throw "pnpm não encontrado. Instale pnpm 11 para validar a interface."
}
& $pnpm.Source check:js
& $pnpm.Source lint:js
& $pnpm.Source format:check
