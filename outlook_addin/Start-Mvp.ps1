[CmdletBinding()]
param([switch]$TrustCertificate, [switch]$Demo)
$ErrorActionPreference='Stop'
$node=(Get-Command node.exe -ErrorAction SilentlyContinue).Source
if (-not $node) {
    $runtime=Get-AppxPackage -Name 'OpenAI.CodexPrimaryRuntime' -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($runtime) {
        $bundled=Join-Path $runtime.InstallLocation 'dependencies\node\bin\node.exe'
        if (Test-Path -LiteralPath $bundled) { $node=$bundled }
    }
}
if (-not $node) { throw 'Necesitas Node.js instalado o disponible en PATH.' }
if ($Demo) { & $node (Join-Path $PSScriptRoot 'server.mjs') --http; exit $LASTEXITCODE }
$localDir=Join-Path $PSScriptRoot '.local'
New-Item -ItemType Directory -Path $localDir -Force | Out-Null
$pfxPath=Join-Path $localDir 'localhost.pfx'
$passwordPath=Join-Path $localDir 'password.txt'
$cerPath=Join-Path $localDir 'localhost.cer'
if (-not (Test-Path -LiteralPath $pfxPath)) {
    $cert=New-SelfSignedCertificate -DnsName 'localhost' -CertStoreLocation 'Cert:\CurrentUser\My' -FriendlyName 'Maximo Outlook MVP localhost' -KeyExportPolicy Exportable -NotAfter (Get-Date).AddDays(30) -TextExtension @('2.5.29.19={text}CA=false')
    $password=[guid]::NewGuid().ToString('N')+[guid]::NewGuid().ToString('N')
    Export-PfxCertificate -Cert $cert -FilePath $pfxPath -Password (ConvertTo-SecureString $password -AsPlainText -Force) | Out-Null
    Export-Certificate -Cert $cert -FilePath $cerPath | Out-Null
    Set-Content -LiteralPath $passwordPath -Value $password -Encoding ascii
}
if ($TrustCertificate) {
    Write-Host 'Se confiará para tu usuario el certificado de desarrollo de localhost, válido durante 30 días.'
    Import-Certificate -FilePath $cerPath -CertStoreLocation 'Cert:\CurrentUser\Root' | Out-Null
}
$publicCert=New-Object System.Security.Cryptography.X509Certificates.X509Certificate2($cerPath)
if ($publicCert.NotAfter -lt (Get-Date)) { throw 'El certificado ha caducado. Usa Remove-DevCertificate.ps1 antes de generar uno nuevo.' }
if (-not (Test-Path -LiteralPath ('Cert:\CurrentUser\Root\'+$publicCert.Thumbprint))) {
    throw 'Falta confiar el certificado local para Outlook. Ejecuta de nuevo con -TrustCertificate si aceptas instalar este certificado de prueba para tu usuario.'
}
& $node (Join-Path $PSScriptRoot 'server.mjs')
exit $LASTEXITCODE
