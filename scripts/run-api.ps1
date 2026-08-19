$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $projectRoot

if (-not (Test-Path ".venv\Scripts\python.exe")) {
    throw "Ambiente ausente. Execute scripts\bootstrap.ps1 primeiro."
}

& ".\.venv\Scripts\python.exe" -m uvicorn api.main:app --host 127.0.0.1 --port 8000 --reload

