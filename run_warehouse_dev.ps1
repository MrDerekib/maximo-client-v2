<#
.SYNOPSIS
Prototipo aislado de almacén. Por defecto abre la demostración con OTs ficticias.
#>
param([switch]$FullApp)
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$python = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $python)) {
    throw 'Crea el entorno de esta carpeta con python -m venv .venv e instala requirements.txt.'
}
$oldDev = $env:MAXIMO_DESKTOP_DEV
$oldWarehouse = $env:MAXIMO_DESKTOP_WAREHOUSE_DEV
try {
    $env:MAXIMO_DESKTOP_DEV = '1'
    $env:MAXIMO_DESKTOP_WAREHOUSE_DEV = '1'
    $entry = if ($FullApp) { 'ui_qt.py' } else { 'tools\warehouse_demo.py' }
    & $python (Join-Path $PSScriptRoot $entry)
    $result = $LASTEXITCODE
} finally {
    $env:MAXIMO_DESKTOP_DEV = $oldDev
    $env:MAXIMO_DESKTOP_WAREHOUSE_DEV = $oldWarehouse
}
exit $result
