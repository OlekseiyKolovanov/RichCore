$ErrorActionPreference = 'Stop'

$Root = Resolve-Path (Join-Path $PSScriptRoot "..")
Set-Location $Root

if (-not (Test-Path (Join-Path $Root '.git'))) {
    Write-Error 'Ця папка не містить git-репозиторію. Виконайте оновлення вручну або використайте клон з GitHub.'
    exit 1
}

Write-Host 'Перевірка стану репозиторію...'
$gitStatus = git status --porcelain
if ($gitStatus) {
    Write-Warning 'У вас є незакомічені зміни. Збережіть їх або відкотіть перед оновленням.'
    git status --short
    exit 1
}

Write-Host 'Отримую оновлення з GitHub...'

git pull --ff-only

if ($LASTEXITCODE -ne 0) {
    Write-Error 'Не вдалося виконати git pull. Перевірте стан гілки або конфлікти.'
    exit $LASTEXITCODE
}

Write-Host 'Оновлення пройшло успішно.'
