<#
.SYNOPSIS
Inicia Maximo Desktop con datos aislados para desarrollo.
#>

param([string]$DeepLink)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$projectRoot = $PSScriptRoot
$python = Join-Path $projectRoot ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $python)) {
    throw "No se encontró el entorno virtual del proyecto: $python. Créalo e instala requirements.txt."
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
