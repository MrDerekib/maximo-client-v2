<#!
.SYNOPSIS
Compila MaximoDesktop como aplicación Windows standalone con Nuitka.

.DESCRIPTION
Usa el Python del entorno virtual del proyecto y deja cada compilación en
release\MaximoDesktop-<versión>. No depende de rutas del usuario que compila.

.PARAMETER Force
Reemplaza la compilación existente de la versión actual.
#>
[CmdletBinding()]
param(
    [switch]$Force,
    [switch]$KeepBuild,
    [string]$PythonPath
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$projectRoot = $PSScriptRoot
$python = if ($PythonPath) {
    (Resolve-Path -LiteralPath $PythonPath).Path
} else {
    Join-Path $projectRoot ".venv\Scripts\python.exe"
}
if (-not (Test-Path -LiteralPath $python)) {
    throw "No se encontró el intérprete Python indicado: $python"
}

$version = (& $python -c "from version import APP_VERSION; print(APP_VERSION)").Trim()
if ($LASTEXITCODE -ne 0 -or -not $version) {
    throw "No se pudo leer la versión de version.py"
}

$releaseRoot = Join-Path $projectRoot "release"
$outputDir = Join-Path $releaseRoot "MaximoDesktop-$version"
if (Test-Path -LiteralPath $outputDir) {
    if (-not $Force) {
        throw "Ya existe $outputDir. Usa -Force para reemplazar solo esa compilación."
    }
    Remove-Item -LiteralPath $outputDir -Recurse -Force
}
New-Item -ItemType Directory -Path $outputDir -Force | Out-Null

$localAppData = [Environment]::GetFolderPath("LocalApplicationData")
$cacheDir = if ($localAppData) {
    Join-Path $localAppData "MaximoDesktop\build-cache\nuitka"
}
else {
    Join-Path $projectRoot ".nuitka-cache"
}
$previousCacheDir = $env:NUITKA_CACHE_DIR
$env:NUITKA_CACHE_DIR = $cacheDir

$nuitkaArguments = @(
    "ui_qt.py",
    "--standalone",
    "--assume-yes-for-downloads",
    "--enable-plugin=pyside6",
    "--include-package=lxml",
    "--include-data-file=$projectRoot\icon.ico=icon.ico",
    "--include-data-file=$projectRoot\seguimiento_options.txt=seguimiento_options.txt",
    "--include-data-dir=$projectRoot\browser_extension=browser_extension",
    "--include-data-dir=$projectRoot\ui_assets=ui_assets",
    "--windows-icon-from-ico=$projectRoot\icon.ico",
    "--windows-console-mode=disable",
    "--product-name=Maximo Desktop",
    "--file-description=Maximo Desktop",
    "--file-version=$version",
    "--product-version=$version",
    "--output-filename=MaximoDesktop.exe",
    "--output-dir=$outputDir",
    "--report=$outputDir\compilation-report.xml"
)

Push-Location $projectRoot
try {
    & $python -m nuitka @nuitkaArguments
    if ($LASTEXITCODE -ne 0) {
        throw "Nuitka terminó con código $LASTEXITCODE."
    }
}
finally {
    Pop-Location
    if ($null -eq $previousCacheDir) {
        Remove-Item Env:NUITKA_CACHE_DIR -ErrorAction SilentlyContinue
    }
    else {
        $env:NUITKA_CACHE_DIR = $previousCacheDir
    }
}

$distribution = Get-ChildItem -LiteralPath $outputDir -Directory |
    Where-Object { $_.Name -like "*.dist" } |
    Select-Object -First 1
if ($null -eq $distribution) {
    throw "Nuitka no generó la carpeta .dist esperada."
}

if (-not $KeepBuild) {
    Get-ChildItem -LiteralPath $outputDir -Directory |
        Where-Object { $_.Name -like "*.build" } |
        Remove-Item -Recurse -Force
}

$packagePath = Join-Path $outputDir "MaximoDesktop-v$version-windows.zip"
Compress-Archive -Path (Join-Path $distribution.FullName "*") -DestinationPath $packagePath -Force

Write-Host "Compilación completada: $($distribution.FullName)" -ForegroundColor Green
Write-Host "Distribuye el contenido completo de esa carpeta, no solo el .exe."
Write-Host "Paquete para la release: $packagePath" -ForegroundColor Green
