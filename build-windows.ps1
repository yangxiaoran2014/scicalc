#requires -Version 5.1
<#
.SYNOPSIS
    Build the standalone SciCalc CMD Windows executable.

.DESCRIPTION
    Requires PyInstaller. Install it once with:
        python -m pip install ".[build]"

    PyInstaller 6.22 has trouble resolving project paths that contain non-ASCII
    characters, so the source is mirrored into a temporary ASCII-only folder
    before packaging. The output is dist\SciCalcCMD.exe.

    The executable is not committed; attach it to a GitHub release.
#>
[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$root = $PSScriptRoot
$env:PYTHONUTF8 = '1'
$env:PYTHONIOENCODING = 'utf-8'

$null = python -c "import PyInstaller" 2>&1
if ($LASTEXITCODE -ne 0) {
    throw 'PyInstaller is not installed. Run: python -m pip install ".[build]"'
}

$tempBase = [System.IO.Path]::GetTempPath()
if ($tempBase -match '[^\x00-\x7F]') {
    $tempBase = 'C:\Users\Public'
}
$work = Join-Path $tempBase ('scicalc-build-' + [guid]::NewGuid().ToString('N'))
$buildOk = $false

try {
    New-Item -ItemType Directory -Path $work | Out-Null
    Copy-Item -Recurse "$root\scicalc" "$work\scicalc"
    Copy-Item "$root\scicalc-cmd.pyw" "$work\"
    Copy-Item -Recurse "$root\assets" "$work\assets"
    Copy-Item -Recurse "$root\packaging" "$work\packaging"

    Push-Location $work
    try {
        python -m PyInstaller --noconfirm --clean "packaging\SciCalcCMD.spec"
        if ($LASTEXITCODE -ne 0) {
            throw "PyInstaller failed with exit code $LASTEXITCODE."
        }
    }
    finally {
        Pop-Location
    }

    $built = Join-Path $work 'dist\SciCalcCMD.exe'
    if (-not (Test-Path $built)) {
        throw "Expected output was not created: $built"
    }

    $destination = Join-Path $root 'dist'
    New-Item -ItemType Directory -Force -Path $destination | Out-Null
    $output = Join-Path $destination 'SciCalcCMD.exe'
    Copy-Item -Force $built $output

    $item = Get-Item $output
    $hash = (Get-FileHash -Algorithm SHA256 $output).Hash
    $buildOk = $true

    Write-Host ''
    Write-Host 'Build complete' -ForegroundColor Green
    Write-Host "  File:   $($item.FullName)"
    Write-Host "  Size:   $([math]::Round($item.Length / 1MB, 2)) MB"
    Write-Host "  SHA256: $hash"
}
finally {
    if ($buildOk) {
        Remove-Item -Recurse -Force $work -ErrorAction SilentlyContinue
    }
    else {
        Write-Warning "Build failed; temporary work directory kept at: $work"
    }
}
