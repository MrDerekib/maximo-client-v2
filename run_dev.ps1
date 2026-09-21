<#
.SYNOPSIS
Inicia la rama de diseño con datos aislados de Maximo Desktop.
#>

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$projectRoot = $PSScriptRoot
$stableProject = Join-Path (Split-Path -Parent $projectRoot) "maximo-client-v2"
$python = @(
    (Join-Path $projectRoot ".venv\Scripts\python.exe"),
    (Join-Path $stableProject ".venv\Scripts\python.exe")
) | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1

if ($null -eq $python) {
    throw "No se encontró un entorno virtual en la rama UI ni en $stableProject"
}

$env:MAXIMO_DESKTOP_DEV = "1"
& $python (Join-Path $projectRoot "gui_main.py")
