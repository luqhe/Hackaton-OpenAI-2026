$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $projectRoot

function Invoke-CheckedCommand {
    param(
        [Parameter(Mandatory = $true)][string]$Command,
        [Parameter(Mandatory = $true)][string[]]$Arguments
    )
    & $Command @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "Command failed with exit code ${LASTEXITCODE}: $Command $($Arguments -join ' ')"
    }
}

$python = ".\.venv\Scripts\python.exe"
Invoke-CheckedCommand $python @("scripts\validate_stage0.py")
Invoke-CheckedCommand $python @("scripts\run_r3_evals.py", "--check")
Invoke-CheckedCommand $python @("-m", "ruff", "check", ".")
Invoke-CheckedCommand $python @(
    "-m", "ruff", "format", "--check", "agent", "api", "guardian_core", "risk_engine", "scripts", "tests"
)
Invoke-CheckedCommand $python @("-m", "pytest")

$pnpm = Get-Command pnpm -ErrorAction SilentlyContinue
if (-not $pnpm) {
    throw "pnpm não encontrado. Instale pnpm 11 para validar a interface."
}
Invoke-CheckedCommand $pnpm.Source @("check:js")
Invoke-CheckedCommand $pnpm.Source @("lint:js")
Invoke-CheckedCommand $pnpm.Source @("format:check")
