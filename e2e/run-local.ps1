# PipPal Public Live UI E2E Release Gate Runner
#
# Authoritative release-gate contract: docs/RELEASE_CHECKLIST.md
# (this runner is Gate 2 of the Core release checklist).
# Reviewer rule for this gate: docs/LIVE_UI_E2E_RELEASE_GATE.md

[CmdletBinding()]
param(
    [switch] $SkipSetup,
    [string] $EvidenceDir,
    [switch] $AllowUnavailable
)

$ErrorActionPreference = 'Stop'

function Get-JUnitCounts {
    param(
        [Parameter(Mandatory = $true)]
        [string] $Path
    )

    $counts = [ordered]@{
        tests = 0
        failures = 0
        errors = 0
        skipped = 0
    }

    if (-not (Test-Path $Path)) {
        return $counts
    }

    [xml] $junit = Get-Content -Raw -Path $Path
    $suites = @()
    if ($junit.testsuites) {
        $suites = @($junit.testsuites.testsuite)
    }
    elseif ($junit.testsuite) {
        $suites = @($junit.testsuite)
    }

    foreach ($suite in $suites) {
        $counts.tests += [int] $suite.tests
        $counts.failures += [int] $suite.failures
        $counts.errors += [int] $suite.errors
        $counts.skipped += [int] $suite.skipped
    }

    return $counts
}

$root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$startedAt = Get-Date
if ([string]::IsNullOrWhiteSpace($EvidenceDir)) {
    $stamp = $startedAt.ToUniversalTime().ToString('yyyyMMddTHHmmssZ')
    $EvidenceDir = Join-Path $root ".e2e\evidence\live-ui-$stamp"
}

New-Item -ItemType Directory -Force -Path $EvidenceDir | Out-Null
$EvidenceDir = (Resolve-Path $EvidenceDir).Path
$pytestLog = Join-Path $EvidenceDir 'pytest-live-ui.log'
$junitXml = Join-Path $EvidenceDir 'pytest-live-ui.junit.xml'
$summaryJson = Join-Path $EvidenceDir 'release-gate-summary.json'
$commandFile = Join-Path $EvidenceDir 'release-gate-command.txt'

$venvDir = Join-Path $root '.e2e\.venv'
$python = Join-Path $venvDir 'Scripts\python.exe'
if (-not (Test-Path $python)) {
    Write-Host "Creating live UI E2E venv: $venvDir" -ForegroundColor Cyan
    py -3.13 -m venv $venvDir
    if ($LASTEXITCODE -ne 0) {
        exit $LASTEXITCODE
    }
}

& $python -m pip install --quiet --upgrade pip
if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
}
& $python -m pip install --quiet -r (Join-Path $root 'e2e\requirements.txt')
if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
}
& $python -m pip install --quiet -e $root
if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
}

$dataRoot = Join-Path $root '.e2e\data\public'
New-Item -ItemType Directory -Force -Path $dataRoot | Out-Null

if (-not $SkipSetup) {
    Write-Host "Preparing public checkout through setup.ps1" -ForegroundColor Cyan
    $env:PIPPAL_DATA_DIR = $dataRoot
    powershell -NoProfile -ExecutionPolicy Bypass -File (Join-Path $root 'setup.ps1')
    if ($LASTEXITCODE -ne 0) {
        exit $LASTEXITCODE
    }
    Remove-Item Env:\PIPPAL_DATA_DIR -ErrorAction SilentlyContinue
}

$env:PIPPAL_E2E_LIVE = '1'
$env:PIPPAL_E2E_PUBLIC_ROOT = $root
$env:PIPPAL_E2E_DATA_ROOT = $dataRoot

$pytestArgs = @(
    '-m',
    'pytest',
    '-ra',
    '--junitxml',
    $junitXml,
    (Join-Path $root 'e2e')
)

@(
    'PipPal public live UI E2E release gate',
    "Started: $($startedAt.ToString('o'))",
    "Command: `"$python`" $($pytestArgs -join ' ')",
    "EvidenceDir: $EvidenceDir",
    "PytestLog: $pytestLog",
    "JUnitXml: $junitXml",
    "SummaryJson: $summaryJson",
    "PublicRoot: $root",
    "DataRoot: $dataRoot",
    'Required environment: PIPPAL_E2E_LIVE=1, PIPPAL_E2E_PUBLIC_ROOT, PIPPAL_E2E_DATA_ROOT',
    'App harness environment: PIPPAL_E2E_COMMAND_SERVER=1 is set only for the launched app process.'
) | Set-Content -Encoding utf8 -Path $commandFile

try {
    Write-Host "Writing live UI E2E evidence to $EvidenceDir" -ForegroundColor Cyan
    $pytestOutput = & $python @pytestArgs 2>&1
    $pytestExitCode = $LASTEXITCODE
    $pytestOutput | Tee-Object -FilePath $pytestLog

    $counts = Get-JUnitCounts -Path $junitXml
    $finalExitCode = $pytestExitCode
    $status = if ($pytestExitCode -eq 0) { 'pass' } else { 'fail' }
    if ($pytestExitCode -eq 0 -and ($counts.tests -eq 0 -or $counts.skipped -gt 0)) {
        if ($AllowUnavailable) {
            $status = 'unavailable'
        }
        else {
            $status = 'blocked'
            $finalExitCode = 5
        }
    }

    $summary = [ordered]@{
        gate = 'pippal-public-live-ui-e2e'
        status = $status
        exit_code = $finalExitCode
        pytest_exit_code = $pytestExitCode
        allow_unavailable = [bool] $AllowUnavailable
        started_at = $startedAt.ToString('o')
        finished_at = (Get-Date).ToString('o')
        command = @($python) + $pytestArgs
        evidence_dir = $EvidenceDir
        log = $pytestLog
        junit_xml = $junitXml
        command_file = $commandFile
        public_root = $root
        data_root = $dataRoot
        tests = $counts.tests
        failures = $counts.failures
        errors = $counts.errors
        skipped = $counts.skipped
        command_server = 'PIPPAL_E2E_COMMAND_SERVER=1 for launched app process'
        reviewer_rule = 'Release pass requires status=pass, exit_code=0, tests>0, failures=0, errors=0, skipped=0.'
    }
    $summary | ConvertTo-Json -Depth 4 | Set-Content -Encoding utf8 -Path $summaryJson

    Write-Host "Live UI E2E gate status: $status" -ForegroundColor Cyan
    Write-Host "Summary: $summaryJson" -ForegroundColor Cyan
    exit $finalExitCode
}
finally {
    Remove-Item Env:\PIPPAL_E2E_LIVE -ErrorAction SilentlyContinue
    Remove-Item Env:\PIPPAL_E2E_PUBLIC_ROOT -ErrorAction SilentlyContinue
    Remove-Item Env:\PIPPAL_E2E_DATA_ROOT -ErrorAction SilentlyContinue
}
