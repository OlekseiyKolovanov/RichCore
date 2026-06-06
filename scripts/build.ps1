$ErrorActionPreference = "Stop"

$Root = Resolve-Path (Join-Path $PSScriptRoot "..")
Set-Location $Root

py -3.14 -m pip install --upgrade pip
py -3.14 -m pip install --upgrade PySide6 pyinstaller
py -3.14 -m PyInstaller --noconfirm --clean RichCore_v12.spec

Write-Host "Built dist\RichCore_v12.exe"
