$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $projectRoot

if (-not (Test-Path ".venv\Scripts\python.exe")) {
    throw "Ambiente ausente. Execute scripts\bootstrap.ps1 primeiro."
}

$env:GUARDIAN_DEMO_MODE = "true"
$env:GUARDIAN_ENVIRONMENT = "development"
$env:GUARDIAN_API_URL = "http://127.0.0.1:8000"

& ".\.venv\Scripts\python.exe" -m uvicorn api.main:app --host 127.0.0.1 --port 8000 --reload
