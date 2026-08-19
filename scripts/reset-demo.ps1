$ErrorActionPreference = "Stop"
$projectRoot = (Resolve-Path (Split-Path -Parent $PSScriptRoot)).Path
$dataRoot = Join-Path $projectRoot ".data"
$resolvedParent = (Resolve-Path (Split-Path -Parent $dataRoot)).Path

if ($resolvedParent -ne $projectRoot -or (Split-Path -Leaf $dataRoot) -ne ".data") {
    throw "Caminho de dados inesperado; reset cancelado."
}

if (Test-Path -LiteralPath $dataRoot) {
    Remove-Item -LiteralPath $dataRoot -Recurse -Force
}
Write-Host "Dados locais da demo removidos. A API recriará o banco inicial no próximo início."

