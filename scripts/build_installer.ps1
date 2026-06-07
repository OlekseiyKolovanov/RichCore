$ErrorActionPreference = "Stop"

$Root = Resolve-Path (Join-Path $PSScriptRoot "..")
Set-Location $Root

& (Join-Path $PSScriptRoot "build.ps1")

$iscc = Get-Command ISCC.exe -ErrorAction SilentlyContinue | Select-Object -First 1 -ExpandProperty Source
if (-not $iscc) {
    $candidates = @(
        (Join-Path $env:LOCALAPPDATA "Programs\Inno Setup 6\ISCC.exe"),
        "C:\Program Files (x86)\Inno Setup 6\ISCC.exe",
        "C:\Program Files\Inno Setup 6\ISCC.exe"
    )
    foreach ($candidate in $candidates) {
        if (Test-Path $candidate) {
            $iscc = $candidate
            break
        }
    }
}

if (-not $iscc) {
    throw "Inno Setup 6 was not found. Install JRSoftware.InnoSetup with winget or from the official site, then run scripts\build_installer.ps1 again."
}

$setupScript = Join-Path $Root "installer\RichCore_v12.iss"
& $iscc $setupScript

$setupPath = Join-Path $Root "dist\RichCore_v12_Setup.exe"
$exePath = Join-Path $Root "dist\RichCore_v12\RichCore_v12.exe"

$signtool = Get-Command signtool.exe -ErrorAction SilentlyContinue | Select-Object -First 1 -ExpandProperty Source
$pfx = $env:RICHCORE_CODESIGN_PFX
$pfxPassword = $env:RICHCORE_CODESIGN_PASSWORD
if ($signtool -and $pfx -and (Test-Path $pfx)) {
    $timestamp = "http://timestamp.digicert.com"
    $signArgs = @("sign", "/fd", "SHA256", "/tr", $timestamp, "/td", "SHA256", "/f", $pfx)
    if ($pfxPassword) {
        $signArgs += @("/p", $pfxPassword)
    }
    foreach ($target in @($exePath, $setupPath)) {
        if (Test-Path $target) {
            & $signtool @signArgs $target
        }
    }
} else {
    Write-Host "Code signing skipped: signtool or RICHCORE_CODESIGN_PFX is not configured."
}

Write-Host "Built dist\RichCore_v12_Setup.exe"
