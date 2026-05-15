# Live UI E2E Release Gate

This checklist is the public Core release gate for live Windows UI behavior.
It is intentionally separate from the default `python -m pytest` suite because
it launches the real desktop app, uses the localhost command server, and
requires a Windows desktop session with Piper assets installed.

## Blocking Command

On a fresh machine, prepare Piper and the default public voice before running
the tests:

```powershell
pwsh -NoProfile -ExecutionPolicy Bypass -File .\e2e\run-local.ps1
```

For routine release review after `.e2e\data\public` already exists:

```powershell
pwsh -NoProfile -ExecutionPolicy Bypass -File .\e2e\run-local.ps1 -SkipSetup
```

For CI or a scripted release workstation, put artifacts in an explicit upload
location:

```powershell
pwsh -NoProfile -ExecutionPolicy Bypass -File .\e2e\run-local.ps1 -SkipSetup -EvidenceDir "$env:RUNNER_TEMP\pippal-live-ui-e2e"
```

Do not use `-AllowUnavailable` for a release pass. That switch is only for
diagnostic CI jobs that need a machine-readable `unavailable` result when a
desktop UI session cannot be provided.

## Evidence Location

By default the runner writes evidence under:

```text
.e2e\evidence\live-ui-<UTC timestamp>\
```

The directory contains:

| File | Reviewer use |
| --- | --- |
| `release-gate-summary.json` | Machine-readable gate status, exit code, test counts, command, paths, and reviewer rule. |
| `pytest-live-ui.log` | Full pytest stdout/stderr for the live UI run. |
| `pytest-live-ui.junit.xml` | CI-friendly test result XML for artifact upload and review annotations. |
| `release-gate-command.txt` | Exact command, data root, evidence root, and environment contract used for the run. |

## Pass Criteria

A public release reviewer may treat the live UI gate as passed only when:

- `release-gate-summary.json` reports `"status": "pass"` and `"exit_code": 0`.
- The summary reports `tests > 0`, `failures = 0`, `errors = 0`, and `skipped = 0`.
- The log shows the app launched from this checkout and not from an installed
  Store/MSIX build.
- The evidence directory is attached to the release PR/checklist or uploaded
  by CI as an artifact.

If the runner exits with status `fail` or `blocked`, the UI environment did not
prove the release gate. Common blockers are a non-Windows runner, no desktop
session, a stale PipPal process already owning the command port, or missing
Piper assets.

## UI State Proven

The live gate proves the public source app can:

- launch with isolated `.e2e\data\public` state;
- expose the test-only command server only for the launched app process through
  `PIPPAL_E2E_COMMAND_SERVER=1`;
- open Settings and Voice Manager through real Tk windows;
- account for actionable Settings controls;
- apply public settings values through live widgets;
- synthesize a Piper WAV and route reader-panel controls through the live engine;
- validate command-server rejection paths and `pippal.open_file` routing.

## Teaching Note

This uses an evidence-wrapper gate. The pattern is to keep the live desktop
tests manual/opt-in, but make their artifact contract deterministic. It was
chosen because release reviewers need proof, while default unit tests must stay
fast and headless. Alternatives are workflow-only enforcement or pure UI
automation screenshots. The tradeoff is an extra script contract, but it gives
local and CI runs the same reviewable evidence.
