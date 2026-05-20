<#
.SYNOPSIS
  PipPal Tier-2 user-journey evidence runner.

.DESCRIPTION
  Runs the e2e/journey suite, which LAUNCHES THE REAL PipPal desktop app
  (a real pywebview WebView2 window appears in YOUR interactive session)
  and drives it over CDP with Playwright.

  This MUST be run by the logged-in interactive user (or a user-session
  scheduled task) — NOT by the Session-0 CI runner, which has no visible
  desktop and cannot show the real window. This is the release / journey
  lane; the per-PR merge gate stays Tier-1 (e2e/web, served + headless).

  Mirrors e2e/run-local.ps1's status / exit-code contract and writes a
  full evidence bundle (log + JUnit XML + JSON summary + per-test
  Playwright trace/video/screenshots + self-contained HTML report)
  under an evidence dir.

.PARAMETER EvidenceDir
  Where to write the evidence bundle (default: a timestamped dir under
  .e2e\evidence\journey-<UTC stamp>).

.PARAMETER K
  Optional pytest -k expression to run a subset (e.g. -K test_j1).

.PARAMETER Runs
  How many times to run the full suite back-to-back (default 1). The
  release evidence expects >= 2 to demonstrate stability.

.PARAMETER NoPublish
  Skip the best-effort `gh workflow run journey-evidence.yml`
  trigger at the end. The evidence bundle is still STAGED to the fixed
  host path either way (so the Tier-2 Evidence Publish workflow can be
  dispatched manually later).

  (Workflow renamed from `tier2-evidence-publish.yml` ->
  `journey-evidence.yml` in the gate-/check-/journey- funkcio-prefix
  rename; the workflow `name:` "Tier-2 Evidence Publish" is unchanged.)

.PARAMETER StageRoot
  Override the fixed staging root (default
  `%LOCALAPPDATA%\pippal-tier2-evidence`). The just-produced bundle is
  copied to `<StageRoot>\latest\` and a timestamped sibling. The
  `journey-evidence.yml` workflow (renamed from
  `tier2-evidence-publish.yml`) reads `<StageRoot>\latest\` on
  the runner host and uploads it as the `tier2-journey-evidence`
  GitHub artifact (Tier-1's equivalent of an attached, downloadable
  report).

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File e2e\journey\run-journey.ps1 -Runs 2
#>
[CmdletBinding()]
param(
    [string] $EvidenceDir,
    [string] $K,
    [int] $Runs = 1,
    [switch] $NoPublish,
    [string] $StageRoot
)

$ErrorActionPreference = 'Stop'

function Get-JUnitCounts {
    param([Parameter(Mandatory = $true)][string] $Path)
    $counts = [ordered]@{ tests = 0; failures = 0; errors = 0; skipped = 0 }
    if (-not (Test-Path $Path)) { return $counts }
    [xml] $junit = Get-Content -Raw -Path $Path
    $suites = @()
    if ($junit.testsuites) { $suites = @($junit.testsuites.testsuite) }
    elseif ($junit.testsuite) { $suites = @($junit.testsuite) }
    foreach ($suite in $suites) {
        $counts.tests += [int] $suite.tests
        $counts.failures += [int] $suite.failures
        $counts.errors += [int] $suite.errors
        $counts.skipped += [int] $suite.skipped
    }
    return $counts
}

function Publish-Tier2Evidence {
    <#
      Stage the just-produced evidence bundle to a FIXED host path so
      the workflow_dispatch `journey-evidence.yml` (renamed from
      `tier2-evidence-publish.yml`; a single job that runs NO journey —
      no desktop needed) can read it from the runner host and
      `actions/upload-artifact@v4` it as `tier2-journey-evidence`
      (Tier-1's equivalent of an attached, downloadable report). This
      is purely additive: it touches only this Tier-2 runner and a
      per-user staging dir; it does not affect Tier-1 or any required
      check.

      Best-effort + non-fatal: a staging/publish failure must NEVER
      change the journey gate's exit code.
    #>
    param(
        [Parameter(Mandatory = $true)][string] $EvidenceDir,
        [Parameter(Mandatory = $true)][string] $StageRoot,
        [Parameter(Mandatory = $true)][string] $RepoRoot,
        [bool] $TriggerPublish = $true
    )
    try {
        $stamp = (Get-Date).ToUniversalTime().ToString('yyyyMMddTHHmmssZ')
        $latest = Join-Path $StageRoot 'latest'
        $timed = Join-Path $StageRoot $stamp
        # Fresh `latest` each run (a clean, predictable artifact source).
        if (Test-Path $latest) { Remove-Item -Recurse -Force $latest }
        New-Item -ItemType Directory -Force -Path $latest | Out-Null
        New-Item -ItemType Directory -Force -Path $timed | Out-Null

        # Copy the WHOLE evidence bundle (report.html, junit, summary
        # json, step logs, per-journey screenshots, trace.zip, the new
        # .mp4 / contact-sheet recordings, app/cdp proof).
        Copy-Item -Recurse -Force -Path (Join-Path $EvidenceDir '*') `
            -Destination $latest
        Copy-Item -Recurse -Force -Path (Join-Path $EvidenceDir '*') `
            -Destination $timed

        # A small manifest so the publish job + reviewers can see at a
        # glance what bundle this is, without opening every file.
        $files = Get-ChildItem -Recurse -File $latest
        $totalBytes = ($files | Measure-Object Length -Sum).Sum
        $manifest = [ordered]@{
            tier = 2
            staged_at = (Get-Date).ToString('o')
            source_evidence_dir = $EvidenceDir
            file_count = $files.Count
            total_bytes = [int64]$totalBytes
            recordings = @(
                $files |
                    Where-Object {
                        $_.Extension -in '.mp4', '.zip' -or
                        $_.Name -like '*.frames.png'
                    } |
                    ForEach-Object {
                        $_.FullName.Substring($latest.Length).TrimStart('\')
                    }
            )
            note = 'Tier-2 user-journey evidence (REAL launched WebView2 app, driven over connect_over_cdp). Trace.zip = scrubbable recording; .mp4/.frames.png = real screen/window capture. See e2e/journey/README.md.'
        }
        $manifestPath = Join-Path $latest 'tier2-evidence-manifest.json'
        $manifest | ConvertTo-Json -Depth 6 |
            Set-Content -Encoding utf8 -Path $manifestPath
        Copy-Item -Force -Path $manifestPath `
            -Destination (Join-Path $timed 'tier2-evidence-manifest.json')

        Write-Host "Staged Tier-2 evidence -> $latest" -ForegroundColor Cyan
        Write-Host ("  ({0} files, {1:N0} bytes; timestamped copy: {2})" -f `
                $files.Count, $totalBytes, $timed) -ForegroundColor Cyan

        if (-not $TriggerPublish) {
            Write-Host "Publish trigger skipped (-NoPublish)." -ForegroundColor Yellow
            return
        }

        # Best-effort: dispatch the publish workflow. `gh` is not on
        # PATH on this host; resolve it explicitly. A failure here is
        # logged and ignored — the bundle is already staged so the
        # workflow can be dispatched manually from the Actions tab.
        $gh = $null
        $ghCmd = Get-Command gh -ErrorAction SilentlyContinue
        if ($ghCmd) { $gh = $ghCmd.Source }
        elseif (Test-Path 'C:\Program Files\GitHub CLI\gh.exe') {
            $gh = 'C:\Program Files\GitHub CLI\gh.exe'
        }
        if (-not $gh) {
            Write-Host "gh CLI not found — staged only; dispatch 'Tier-2 Evidence Publish' manually." -ForegroundColor Yellow
            return
        }
        $branch = (& git -C $RepoRoot rev-parse --abbrev-ref HEAD).Trim()
        if ([string]::IsNullOrWhiteSpace($branch)) { $branch = 'feat/web-ui-migration' }
        Write-Host "Dispatching Tier-2 Evidence Publish workflow on '$branch'…" -ForegroundColor Cyan
        # Workflow filename: journey-evidence.yml (renamed from
        # tier2-evidence-publish.yml; workflow `name:` "Tier-2 Evidence
        # Publish" unchanged, so the Actions UI label is the same).
        & $gh workflow run journey-evidence.yml --ref $branch
        if ($LASTEXITCODE -eq 0) {
            Write-Host "Triggered. Download 'tier2-journey-evidence' from the 'Tier-2 Evidence Publish' workflow run." -ForegroundColor Green
        }
        else {
            Write-Host "gh workflow run returned $LASTEXITCODE — staged OK; dispatch manually if needed." -ForegroundColor Yellow
        }
    }
    catch {
        Write-Host "Tier-2 evidence staging/publish failed (non-fatal): $($_.Exception.Message)" -ForegroundColor Yellow
    }
}

# Repo root = two levels up from e2e/journey/.
$root = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$startedAt = Get-Date
if ([string]::IsNullOrWhiteSpace($EvidenceDir)) {
    $stamp = $startedAt.ToUniversalTime().ToString('yyyyMMddTHHmmssZ')
    $EvidenceDir = Join-Path $root ".e2e\evidence\journey-$stamp"
}
New-Item -ItemType Directory -Force -Path $EvidenceDir | Out-Null
$EvidenceDir = (Resolve-Path $EvidenceDir).Path

# Fixed per-user staging root the publish workflow reads from the
# runner host (Tier-1 uploads its report as a CI artifact; Tier-2
# can't run on the Session-0 runner so the logged-in run stages the
# bundle here and the workflow_dispatch publish job uploads it).
if ([string]::IsNullOrWhiteSpace($StageRoot)) {
    $localAppData = $env:LOCALAPPDATA
    if ([string]::IsNullOrWhiteSpace($localAppData)) {
        $localAppData = Join-Path $env:USERPROFILE 'AppData\Local'
    }
    $StageRoot = Join-Path $localAppData 'pippal-tier2-evidence'
}
New-Item -ItemType Directory -Force -Path $StageRoot | Out-Null
$StageRoot = (Resolve-Path $StageRoot).Path

$pytestLog = Join-Path $EvidenceDir 'pytest-journey.log'
$junitXml = Join-Path $EvidenceDir 'pytest-journey.junit.xml'
$summaryJson = Join-Path $EvidenceDir 'journey-gate-summary.json'
$commandFile = Join-Path $EvidenceDir 'journey-gate-command.txt'
$artifactsDir = Join-Path $EvidenceDir 'playwright-artifacts'
$htmlReport = Join-Path $EvidenceDir 'report.html'
New-Item -ItemType Directory -Force -Path $artifactsDir | Out-Null

# Reuse the same isolated venv layout e2e/run-local.ps1 uses, but a
# distinct dir so the two tiers never share interpreters/state. Real
# Python is py -3.11 on this machine (the `python` alias is the MS
# Store stub).
$venvDir = Join-Path $root '.e2e\.venv-journey'
$python = Join-Path $venvDir 'Scripts\python.exe'
if (-not (Test-Path $python)) {
    Write-Host "Creating journey E2E venv: $venvDir" -ForegroundColor Cyan
    py -3.11 -m venv $venvDir
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}

& $python -m pip install --quiet --upgrade pip
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
& $python -m pip install --quiet -e $root
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
& $python -m pip install --quiet -r (Join-Path $root 'e2e\web\requirements.txt')
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
& $python -m pip install --quiet pywebview
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
# Test-only: Pillow lets the recorder's no-ffmpeg fallback assemble
# the dense contact-sheet recording. Additive + best-effort — if the
# install fails the recorder simply keeps the numbered PNG frames (it
# is non-fatal either way), so do NOT fail the run on it.
& $python -m pip install --quiet pillow
if ($LASTEXITCODE -ne 0) {
    Write-Host "pillow install failed (non-fatal — recorder keeps numbered frames)" -ForegroundColor Yellow
    $global:LASTEXITCODE = 0
}
& $python -m playwright install chromium | Out-Null

# UTF-8 IO so the journey step glyphs (→ / ✓) render in a cp1252 host.
$env:PYTHONUTF8 = '1'
$env:PYTHONIOENCODING = 'utf-8'
# Tier-2 opt-in gate (conftest skips without it). NOT PIPPAL_E2E_LIVE
# (that is the Tk live-desktop gate).
$env:PIPPAL_JOURNEY_LIVE = '1'
# The conftest drops a real screenshot of the live desktop window +
# the launched app's own log + the CDP build string per journey here,
# proving a REAL window (WebView2 'Edg/...') was driven.
$env:PIPPAL_JOURNEY_EVIDENCE_DIR = $artifactsDir

$pytestArgs = @(
    '-m', 'pytest',
    (Join-Path $root 'e2e\journey'),
    '-v', '-rA', '--log-cli-level=INFO',
    '--junitxml', $junitXml,
    "--html=$htmlReport", '--self-contained-html'
)
if (-not [string]::IsNullOrWhiteSpace($K)) {
    $pytestArgs += @('-k', $K)
}

@(
    'PipPal Tier-2 user-journey evidence run (REAL launched desktop app)',
    "Started: $($startedAt.ToString('o'))",
    "Command: `"$python`" $($pytestArgs -join ' ')",
    "Runs: $Runs",
    "EvidenceDir: $EvidenceDir",
    "PytestLog: $pytestLog",
    "JUnitXml: $junitXml",
    "SummaryJson: $summaryJson",
    'Required environment: PIPPAL_JOURNEY_LIVE=1 + a VISIBLE interactive desktop session.',
    'This is the release/journey lane. The per-PR merge gate stays Tier-1 (e2e/web, served+headless).'
) | Set-Content -Encoding utf8 -Path $commandFile

$overallExit = 0
$lastCounts = $null
try {
    for ($i = 1; $i -le $Runs; $i++) {
        Write-Host "=== Journey run $i / $Runs ===" -ForegroundColor Cyan
        $runLog = if ($Runs -gt 1) {
            Join-Path $EvidenceDir ("pytest-journey.run{0}.log" -f $i)
        }
        else { $pytestLog }
        $out = & $python @pytestArgs 2>&1
        $exit = $LASTEXITCODE
        # UTF-8 (not PowerShell's default UTF-16) so the journey step
        # glyphs (-> / OK marks) stay readable in the evidence log.
        $out | Out-String | Out-File -Encoding utf8 -FilePath $runLog
        Write-Host ($out | Out-String)
        if ($Runs -gt 1) {
            $out | Out-String | Add-Content -Encoding utf8 -Path $pytestLog
        }
        $lastCounts = Get-JUnitCounts -Path $junitXml
        Write-Host ("run {0}: exit={1} tests={2} failures={3} errors={4} skipped={5}" -f `
                $i, $exit, $lastCounts.tests, $lastCounts.failures, `
                $lastCounts.errors, $lastCounts.skipped) -ForegroundColor Cyan
        if ($exit -ne 0) { $overallExit = $exit }
    }

    $counts = $lastCounts
    $status = if ($overallExit -eq 0) { 'pass' } else { 'fail' }
    $finalExit = $overallExit
    if ($overallExit -eq 0 -and ($counts.tests -eq 0 -or $counts.skipped -gt 0)) {
        $status = 'blocked'
        $finalExit = 5
    }

    $summary = [ordered]@{
        gate = 'pippal-tier2-user-journey'
        tier = 2
        lane = 'release/journey (NOT the per-PR merge gate; Tier-1 e2e/web stays that)'
        status = $status
        exit_code = $finalExit
        runs = $Runs
        started_at = $startedAt.ToString('o')
        finished_at = (Get-Date).ToString('o')
        command = @($python) + $pytestArgs
        evidence_dir = $EvidenceDir
        log = $pytestLog
        junit_xml = $junitXml
        playwright_artifacts = $artifactsDir
        html_report = $htmlReport
        stage_root = $StageRoot
        staged_latest = (Join-Path $StageRoot 'latest')
        publish_workflow = 'journey-evidence.yml (renamed from tier2-evidence-publish.yml; workflow_dispatch only; uploads artifact tier2-journey-evidence)'
        tests = $counts.tests
        failures = $counts.failures
        errors = $counts.errors
        skipped = $counts.skipped
        drives = 'the REAL launched pywebview WebView2 desktop app via CDP'
        reviewer_rule = 'Journey pass requires status=pass, exit_code=0, tests>0, failures=0, errors=0, skipped=0, runs>=2.'
    }
    $summary | ConvertTo-Json -Depth 5 | Set-Content -Encoding utf8 -Path $summaryJson

    Write-Host "Journey gate status: $status" -ForegroundColor Cyan
    Write-Host "Summary: $summaryJson" -ForegroundColor Cyan
    Write-Host "Evidence: $EvidenceDir" -ForegroundColor Cyan

    # Stage the bundle to the fixed host path and (best-effort) trigger
    # the workflow_dispatch publish so the Tier-2 evidence becomes a
    # downloadable GitHub artifact like Tier-1's. Non-fatal: it never
    # changes $finalExit.
    Publish-Tier2Evidence -EvidenceDir $EvidenceDir -StageRoot $StageRoot `
        -RepoRoot $root -TriggerPublish (-not $NoPublish.IsPresent)

    exit $finalExit
}
finally {
    Remove-Item Env:\PIPPAL_JOURNEY_LIVE -ErrorAction SilentlyContinue
    Remove-Item Env:\PIPPAL_JOURNEY_EVIDENCE_DIR -ErrorAction SilentlyContinue
}
