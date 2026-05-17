# PipPal Public Selected-Text UI Smokes Runner
#
# Authoritative release-gate contract: docs/RELEASE_CHECKLIST.md
# (this runner is Gate 3 of the Core release checklist).
#
# Maintained release-gate runner for issues #62, #63, and #61. Drives
# Notepad, Edge (webpage + built-in PDF viewer), Acrobat (when
# installed), VS Code / Notepad++ (editor row), Windows Terminal /
# legacy PowerShell console (terminal row), and Teams / Outlook /
# Discord (chat / mail row) directly to validate
# `pippal.clipboard_capture.capture_selection` on a real Windows
# desktop session. The #61 daily-use rows do not gate release on their
# own; their results feed the SELECTED_TEXT_RELIABILITY.md matrix.
#
# Unlike e2e\run-local.ps1, this runner does NOT launch the PipPal
# desktop app. It exercises only the selected-text capture helper
# against foreign apps, because that is the release-gate question
# issue #62 is asking ("did v0.2.5 regress Notepad/browser capture?").
#
# Status contract matches e2e\run-local.ps1 for reviewer consistency:
#   pass        -> exit 0, all smokes green
#   fail        -> exit non-zero, a smoke failed
#   blocked     -> exit 5, the harness could not collect or all skipped
#   unavailable -> exit 0, ALLOWED only with -AllowUnavailable
#
# Skipped runs are NOT silently green. Without -AllowUnavailable a
# zero-test or all-skipped result is `blocked`. This is intentional:
# the smokes are maintained, not "green by default."

[CmdletBinding()]
param(
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
    $EvidenceDir = Join-Path $root ".e2e\evidence\ui-smokes-$stamp"
}

New-Item -ItemType Directory -Force -Path $EvidenceDir | Out-Null
$EvidenceDir = (Resolve-Path $EvidenceDir).Path
$pytestLog = Join-Path $EvidenceDir 'pytest-ui-smokes.log'
$junitXml = Join-Path $EvidenceDir 'pytest-ui-smokes.junit.xml'
$summaryJson = Join-Path $EvidenceDir 'ui-smokes-summary.json'
$commandFile = Join-Path $EvidenceDir 'ui-smokes-command.txt'

$python = (Get-Command py -ErrorAction SilentlyContinue)
if ($null -eq $python) {
    Write-Host "py.exe launcher not found. Install Python from python.org." -ForegroundColor Red
    exit 2
}

# Use the live UI E2E venv if it already exists, otherwise the system
# Python. The smokes only need pyperclip + pytest, both already in the
# project dev deps. We do not insist on a venv because this runner is
# intended to be cheap to invoke on any release-review workstation.
$venvPython = Join-Path $root '.e2e\.venv\Scripts\python.exe'
if (Test-Path $venvPython) {
    $pythonExe = $venvPython
}
else {
    $pythonExe = (Get-Command py).Source
}

$env:PIPPAL_UI_SMOKES = '1'
$env:PIPPAL_UI_SMOKES_EVIDENCE_DIR = $EvidenceDir
$env:PYTHONPATH = (Join-Path $root 'src')

$pytestArgs = @(
    '-m',
    'pytest',
    '-ra',
    '--junitxml',
    $junitXml,
    (Join-Path $root 'tests\ui_smokes')
)

@(
    'PipPal public selected-text UI smokes (issues #62, #63, #61)',
    "Started: $($startedAt.ToString('o'))",
    "Command: `"$pythonExe`" $($pytestArgs -join ' ')",
    "EvidenceDir: $EvidenceDir",
    "PytestLog: $pytestLog",
    "JUnitXml: $junitXml",
    "SummaryJson: $summaryJson",
    "Repo root: $root",
    'Required environment: PIPPAL_UI_SMOKES=1, Windows desktop session, Notepad, Edge',
    'Per-smoke evidence: <EvidenceDir>\<smoke_id>.json (foreign app version, fixture, captured text, clipboard restoration).'
) | Set-Content -Encoding utf8 -Path $commandFile

try {
    Write-Host "Writing UI smokes evidence to $EvidenceDir" -ForegroundColor Cyan
    $pytestOutput = & $pythonExe @pytestArgs 2>&1
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
        gate = 'pippal-public-ui-smokes-issues-62-63-61'
        status = $status
        exit_code = $finalExitCode
        pytest_exit_code = $pytestExitCode
        allow_unavailable = [bool] $AllowUnavailable
        started_at = $startedAt.ToString('o')
        finished_at = (Get-Date).ToString('o')
        command = @($pythonExe) + $pytestArgs
        evidence_dir = $EvidenceDir
        log = $pytestLog
        junit_xml = $junitXml
        command_file = $commandFile
        repo_root = $root
        tests = $counts.tests
        failures = $counts.failures
        errors = $counts.errors
        skipped = $counts.skipped
        reviewer_rule = 'Release pass requires status=pass, exit_code=0, tests>0, failures=0, errors=0, skipped=0.'
        surfaces_proven = @(
            'Notepad selected-text happy path',
            'Notepad no-selection clipboard-restoration recovery',
            'Edge webpage selected-text happy path',
            'Edge built-in PDF viewer selected-text happy path (issue #63)',
            'Edge built-in PDF viewer image-only unsupported recovery (issue #63)',
            'Acrobat / Adobe Reader selected-text happy path or unavailable (issue #63)',
            'VS Code selected-text happy path or unavailable (issue #61)',
            'Notepad++ selected-text happy path or unavailable (issue #61)',
            'Windows Terminal buffer happy path or blocked (issue #61)',
            'Legacy powershell.exe console blocked (issue #61)',
            'Teams chat body blocked / unavailable (issue #61)',
            'Outlook message body blocked / unavailable (issue #61)',
            'Discord message body blocked / unavailable (issue #61)'
        )
    }
    $summary | ConvertTo-Json -Depth 4 | Set-Content -Encoding utf8 -Path $summaryJson

    Write-Host "UI smokes gate status: $status" -ForegroundColor Cyan
    Write-Host "Summary: $summaryJson" -ForegroundColor Cyan
    exit $finalExitCode
}
finally {
    Remove-Item Env:\PIPPAL_UI_SMOKES -ErrorAction SilentlyContinue
    Remove-Item Env:\PIPPAL_UI_SMOKES_EVIDENCE_DIR -ErrorAction SilentlyContinue
    Remove-Item Env:\PYTHONPATH -ErrorAction SilentlyContinue
}
