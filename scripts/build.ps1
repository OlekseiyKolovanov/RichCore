$ErrorActionPreference = "Stop"

$Root = Resolve-Path (Join-Path $PSScriptRoot "..")
Set-Location $Root

py -3.14 -m pip install --upgrade pip
py -3.14 -m pip install --upgrade PySide6 pyinstaller
py -3.14 -m PyInstaller --noconfirm --clean RichCore_v12.spec

$DistDir = Join-Path $Root "dist\RichCore_v12"
$ZipPath = Join-Path $Root "dist\RichCore_v12.zip"
if (Test-Path $ZipPath) {
    Remove-Item -LiteralPath $ZipPath -Force
}

$archiveBuilt = $false
for ($attempt = 1; $attempt -le 8; $attempt++) {
    try {
        Compress-Archive -Path (Join-Path $DistDir "*") -DestinationPath $ZipPath -Force
        $archiveBuilt = $true
        break
    } catch {
        if ($attempt -eq 8) {
            throw
        }
        Start-Sleep -Milliseconds (500 * $attempt)
        if (Test-Path $ZipPath) {
            Remove-Item -LiteralPath $ZipPath -Force -ErrorAction SilentlyContinue
        }
    }
}

Write-Host "Built dist\RichCore_v12\RichCore_v12.exe"
Write-Host "Built dist\RichCore_v12.zip"
