$ErrorActionPreference='Stop'
$localDir=Join-Path $PSScriptRoot '.local'
$cerPath=Join-Path $localDir 'localhost.cer'
if (Test-Path -LiteralPath $cerPath) {
    $cert=New-Object System.Security.Cryptography.X509Certificates.X509Certificate2($cerPath)
    foreach ($store in @('Root','My')) {
        $entry='Cert:\CurrentUser\'+$store+'\'+$cert.Thumbprint
        if (Test-Path -LiteralPath $entry) { Remove-Item -LiteralPath $entry }
    }
}
foreach ($name in @('localhost.pfx','localhost.cer','password.txt')) {
    $file=Join-Path $localDir $name
    if (Test-Path -LiteralPath $file) { Remove-Item -LiteralPath $file }
}
Write-Host 'Certificado de prueba eliminado. No se han modificado otros certificados.'
