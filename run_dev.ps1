<#
.SYNOPSIS
Inicia la rama de diseño con datos aislados de Maximo Desktop.
#>

param([string]$DeepLink)

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

$stableInstance = Get-Process -Name "MaximoDesktop" -ErrorAction SilentlyContinue |
    Select-Object -First 1
if ($null -ne $stableInstance) {
    $message = "Cierra Maximo Desktop estable antes de abrir la UI de desarrollo.`n`nProceso detectado: PID $($stableInstance.Id)"
    Write-Host $message -ForegroundColor Yellow
    Add-Type -AssemblyName PresentationFramework
    [System.Windows.MessageBox]::Show(
        $message,
        "Maximo Desktop - UI de desarrollo",
        [System.Windows.MessageBoxButton]::OK,
        [System.Windows.MessageBoxImage]::Warning
    ) | Out-Null
    exit 1
}

$env:MAXIMO_DESKTOP_DEV = "1"
$arguments = @((Join-Path $projectRoot "ui_qt.py"))
if ($DeepLink) { $arguments += $DeepLink }
& $python @arguments
