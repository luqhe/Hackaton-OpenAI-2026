$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $projectRoot

if (-not (Test-Path ".venv\Scripts\python.exe")) {
    $python = Get-Command python3 -ErrorAction SilentlyContinue
    if (-not $python) { $python = Get-Command python -ErrorAction SilentlyContinue }
    if (-not $python) { throw "Python 3.11+ não foi encontrado no PATH." }
    & $python.Source -m venv .venv
}

& ".\.venv\Scripts\python.exe" -m pip install -r requirements.txt
Write-Host "Guardian pronto. Execute scripts\run-api.ps1."

