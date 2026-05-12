[CmdletBinding()]
param(
    [switch] $SkipSetup
)

$ErrorActionPreference = 'Stop'

$root = Resolve-Path (Join-Path $PSScriptRoot '..')
$venvDir = Join-Path $root '.e2e\.venv'
$python = Join-Path $venvDir 'Scripts\python.exe'
if (-not (Test-Path $python)) {
    Write-Host "Creating live UI E2E venv: $venvDir" -ForegroundColor Cyan
    py -3.13 -m venv $venvDir
}

& $python -m pip install --quiet --upgrade pip
& $python -m pip install --quiet -r (Join-Path $root 'e2e\requirements.txt')
& $python -m pip install --quiet -e $root

$dataRoot = Join-Path $root '.e2e\data\public'
New-Item -ItemType Directory -Force -Path $dataRoot | Out-Null

if (-not $SkipSetup) {
    Write-Host "Preparing public checkout through setup.ps1" -ForegroundColor Cyan
    $env:PIPPAL_DATA_DIR = $dataRoot
    powershell -NoProfile -ExecutionPolicy Bypass -File (Join-Path $root 'setup.ps1')
    Remove-Item Env:\PIPPAL_DATA_DIR -ErrorAction SilentlyContinue
}

$env:PIPPAL_E2E_LIVE = '1'
$env:PIPPAL_E2E_PUBLIC_ROOT = $root
$env:PIPPAL_E2E_DATA_ROOT = $dataRoot

try {
    & $python -m pytest -ra (Join-Path $root 'e2e')
    exit $LASTEXITCODE
}
finally {
    Remove-Item Env:\PIPPAL_E2E_LIVE -ErrorAction SilentlyContinue
    Remove-Item Env:\PIPPAL_E2E_PUBLIC_ROOT -ErrorAction SilentlyContinue
    Remove-Item Env:\PIPPAL_E2E_DATA_ROOT -ErrorAction SilentlyContinue
}
