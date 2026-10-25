#requires -Version 5.1
<#
.SYNOPSIS
    Sign a local SciCalc CMD build with a self-signed test certificate.

.DESCRIPTION
    Creates a local test root CA and a code-signing certificate in
    Cert:\CurrentUser\My, and signs a copy of the executable with SHA-256 and
    an RFC 3161 timestamp. The public root certificate is exported, but it is
    NOT installed into a trust store automatically.

    The source executable is never modified. The signed copy is written to
    dist\signed\ by default, together with its SHA-256 file and the public
    root certificate.

    IMPORTANT: This signature is for local testing only. Because the test root
    is not publicly trusted, Windows still reports an unknown publisher and
    SmartScreen can still warn. Do not present this build as publicly trusted.

    To make the signature locally trusted, an administrator or the current
    user can import SciCalc-LocalTest-RootCA.cer into Trusted Root
    Certification Authorities. Remove it later with:
        certutil -user -delstore Root <root thumbprint>
    and delete the certificates from Cert:\CurrentUser\My.

.PARAMETER SourcePath
    Unsigned executable to copy and sign.

.PARAMETER OutputDirectory
    Destination for the signed copy, checksum, and public root certificate.

.PARAMETER TimestampUrl
    RFC 3161 timestamp service. Ignored with -NoTimestamp.

.PARAMETER NoTimestamp
    Skip timestamping. The signature then expires with the certificate.
#>
[CmdletBinding()]
param(
    [string]$SourcePath,
    [string]$OutputDirectory,
    [string]$TimestampUrl = 'http://timestamp.digicert.com',
    [switch]$NoTimestamp
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

if (-not $SourcePath) {
    $SourcePath = Join-Path $PSScriptRoot 'dist\SciCalcCMD-1.1.1-windows-x64.exe'
}
if (-not $OutputDirectory) {
    $OutputDirectory = Join-Path $PSScriptRoot 'dist\signed'
}

$rootSubject = 'CN=SciCalc Development Root CA (Local Test), O=SciCalc'
$signingSubject = 'CN=SciCalc Development Signing (Local Test), O=SciCalc'
$now = Get-Date

function Find-SignTool {
    $candidates = @()

    $command = Get-Command signtool.exe -ErrorAction SilentlyContinue
    if ($command) {
        $candidates += $command.Source
    }

    $kits = Join-Path ${env:ProgramFiles(x86)} 'Windows Kits\10\bin'
    if (Test-Path $kits) {
        $candidates += Get-ChildItem $kits -Recurse -Filter signtool.exe -ErrorAction SilentlyContinue |
            Where-Object { $_.FullName -match '\\x64\\signtool\.exe$' } |
            Select-Object -ExpandProperty FullName
    }

    $candidates = $candidates | Where-Object { $_ -and (Test-Path $_) } | Select-Object -Unique
    if (-not $candidates) {
        throw 'signtool.exe was not found. Install the Windows SDK signing tools.'
    }

    return $candidates | Sort-Object -Descending | Select-Object -First 1
}

function Find-TestRoot {
    Get-ChildItem 'Cert:\CurrentUser\My' |
        Where-Object {
            $_.Subject -like '*SciCalc Development Root CA (Local Test)*' -and
            $_.HasPrivateKey -and
            $_.NotAfter -gt $now.AddDays(30)
        } |
        Sort-Object NotAfter -Descending |
        Select-Object -First 1
}

function Find-TestSigner {
    param([System.Security.Cryptography.X509Certificates.X509Certificate2]$Root)

    Get-ChildItem 'Cert:\CurrentUser\My' -CodeSigningCert |
        Where-Object {
            $_.Subject -like '*SciCalc Development Signing (Local Test)*' -and
            $_.HasPrivateKey -and
            $_.NotAfter -gt $now.AddDays(30) -and
            $_.Issuer -eq $Root.Subject
        } |
        Sort-Object NotAfter -Descending |
        Select-Object -First 1
}

if (-not (Test-Path -LiteralPath $SourcePath)) {
    throw "Source executable not found: $SourcePath"
}

$source = Get-Item -LiteralPath $SourcePath
$signTool = Find-SignTool
New-Item -ItemType Directory -Force -Path $OutputDirectory | Out-Null

$root = Find-TestRoot
if (-not $root) {
    Write-Host 'Creating local test root CA...'
    $root = New-SelfSignedCertificate `
        -Type Custom `
        -Subject $rootSubject `
        -FriendlyName 'SciCalc local test root CA - NOT for public distribution' `
        -KeyAlgorithm RSA `
        -KeyLength 3072 `
        -HashAlgorithm SHA256 `
        -KeyUsage 'CertSign', 'CRLSign', 'DigitalSignature' `
        -KeyExportPolicy NonExportable `
        -TextExtension @('2.5.29.19={text}ca=1&pathlength=1') `
        -CertStoreLocation 'Cert:\CurrentUser\My' `
        -NotBefore $now.AddDays(-1) `
        -NotAfter $now.AddYears(5)
}

$signer = Find-TestSigner -Root $root
if (-not $signer) {
    Write-Host 'Creating local test code-signing certificate...'
    $signer = New-SelfSignedCertificate `
        -Type CodeSigningCert `
        -Subject $signingSubject `
        -FriendlyName 'SciCalc local test signing - NOT for public distribution' `
        -KeyAlgorithm RSA `
        -KeyLength 3072 `
        -HashAlgorithm SHA256 `
        -KeyUsage 'DigitalSignature' `
        -KeyExportPolicy NonExportable `
        -TextExtension @('2.5.29.19={text}ca=0') `
        -CertStoreLocation 'Cert:\CurrentUser\My' `
        -Signer $root `
        -NotBefore $now.AddDays(-1) `
        -NotAfter $now.AddYears(3)
}

$rootCer = Join-Path $OutputDirectory 'SciCalc-LocalTest-RootCA.cer'
Export-Certificate -Cert $root -FilePath $rootCer -Type CERT -Force | Out-Null

$outputName = $source.Name
$signedPath = Join-Path $OutputDirectory $outputName
Copy-Item -LiteralPath $source.FullName -Destination $signedPath -Force

$signArguments = @(
    'sign',
    '/sha1', $signer.Thumbprint,
    '/fd', 'SHA256',
    '/d', 'SciCalc CMD',
    '/du', 'https://github.com/yangxiaoran2014/scicalc'
)

if (-not $NoTimestamp) {
    $signArguments += @('/td', 'SHA256', '/tr', $TimestampUrl)
}

Write-Host 'Signing...'
& $signTool @signArguments $signedPath
if ($LASTEXITCODE -ne 0 -and -not $NoTimestamp) {
    Write-Warning "Timestamping failed; retrying without a timestamp."
    Copy-Item -LiteralPath $source.FullName -Destination $signedPath -Force
    $signArguments = @(
        'sign',
        '/sha1', $signer.Thumbprint,
        '/fd', 'SHA256',
        '/d', 'SciCalc CMD',
        '/du', 'https://github.com/yangxiaoran2014/scicalc'
    )
    & $signTool @signArguments $signedPath
}
if ($LASTEXITCODE -ne 0) {
    throw "signtool sign failed with exit code $LASTEXITCODE."
}

Write-Host 'Verifying...'
$signature = Get-AuthenticodeSignature -LiteralPath $signedPath
if (-not $signature.SignerCertificate) {
    throw "No signer certificate was found: $($signature.StatusMessage)"
}
if ($signature.SignerCertificate.Thumbprint -ne $signer.Thumbprint) {
    throw 'The signature was not created by the expected test certificate.'
}

$chainTrusted = $signature.Status -eq 'Valid'
if (-not $chainTrusted) {
    if ($signature.Status -notin @('UnknownError', 'NotTrusted')) {
        throw "Authenticode status is $($signature.Status): $($signature.StatusMessage)"
    }

    # A self-signed root is not in a trust store. signtool then reports
    # CERT_E_UNTRUSTEDROOT (0x800B0109) or CERT_E_CHAINING (0x800B010A)
    # after it has validated the signature and signer information.
    $previousErrorAction = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try {
        $verifyOutput = (& $signTool verify /pa /v $signedPath 2>&1 | Out-String)
        $verifyCode = $LASTEXITCODE
    }
    finally {
        $ErrorActionPreference = $previousErrorAction
    }

    if ($verifyCode -ne 0 -and
        $verifyOutput -notmatch '0x800B0109' -and
        $verifyOutput -notmatch '0x800B010A' -and
        $verifyOutput -notmatch 'not trusted by the trust provider' -and
        $verifyOutput -notmatch 'terminated in a root') {
        throw "signtool verify failed with exit code $verifyCode.`n$verifyOutput"
    }
}

$hash = (Get-FileHash -Algorithm SHA256 -LiteralPath $signedPath).Hash
$checksumPath = Join-Path $OutputDirectory ($outputName + '.sha256')
Set-Content -LiteralPath $checksumPath -Value "$hash *$outputName" -Encoding ASCII

$item = Get-Item -LiteralPath $signedPath
Write-Host ''
Write-Host 'Test signing complete' -ForegroundColor Green
Write-Host "  File:           $($item.FullName)"
Write-Host "  Size:           $([math]::Round($item.Length / 1MB, 2)) MB"
Write-Host "  SHA256:         $hash"
if ($chainTrusted) {
    Write-Host "  Signature:      Valid (test root is trusted on this PC)"
}
else {
    Write-Host "  Signature:      Present; test root is not trusted on this PC"
}
Write-Host "  Signer:         $($signer.Subject)"
Write-Host "  Signer thumb:   $($signer.Thumbprint)"
Write-Host "  Root cert:      $rootCer"
Write-Host "  Root thumb:     $($root.Thumbprint)"
Write-Host "  Source kept:    $($source.FullName)"
Write-Host ''
Write-Host 'To trust this test root for the current user, install the .cer above'
Write-Host 'into Trusted Root Certification Authorities. Remove it with:'
Write-Host "  certutil -user -delstore Root $($root.Thumbprint)"
Write-Host 'Remove the signing certificates with:'
Write-Host '  Get-ChildItem Cert:\CurrentUser\My | Where-Object Subject -like "*SciCalc Development*" | Remove-Item -DeleteKey'
Write-Host ''
Write-Warning 'This is a local test signature. Other PCs do not trust this root and will still show an unknown publisher / SmartScreen warning.'
