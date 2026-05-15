# PipPal Public Live UI E2E

Manual, Windows-only tests for the public source app. The regular
`python -m pytest` suite does not run these; use the local runner when
you want to exercise the real desktop session.

## Coverage

```text
runner
  |
  +-- prepare .e2e\.venv
  +-- install this checkout in editable mode
  +-- optionally run setup.ps1 for piper.exe and the default voice
  |
  +-- public source app
        |
        +-- launch reader_app.py with an isolated PIPPAL_DATA_DIR
        +-- open live Settings
        +-- assert the runtime registry exposes only the public core
        +-- inventory every Settings control and fail on unaccounted controls
        +-- type text fields character by character
        +-- change selectors, checkboxes, sliders, and spinboxes
        +-- click Settings buttons and public links without opening a browser
        +-- open Voice Manager, select filters, type Search, and close it
        +-- synthesize and play a real Piper WAV
        +-- click reader panel previous/replay/next/close controls
        +-- validate command-server rejection paths
        +-- route a text file through pippal.open_file
```

The harness uses the app's localhost command server for deterministic
native UI control. It still launches the real app. Text input is sent
one character at a time through live Tk widgets, and the manifest check
means a newly added actionable control must be covered explicitly.

The read-aloud tests assert the real backend class and a generated
RIFF/WAVE chunk while playback is active. They do not assert physical
speaker output; that requires a machine-level loopback capture device.

## Run

This runner is **Gate 2** of the Core release checklist. The authoritative,
named release checklist is
[docs/RELEASE_CHECKLIST.md](../docs/RELEASE_CHECKLIST.md); the reviewer rule
for this specific gate is in
[docs/LIVE_UI_E2E_RELEASE_GATE.md](../docs/LIVE_UI_E2E_RELEASE_GATE.md).
The companion foreign-app selected-text smokes (`run-ui-smokes.ps1`) are
**Gate 3**.

The runner writes a log, JUnit XML, command record, and JSON summary for every
run under `.e2e\evidence\live-ui-<UTC timestamp>\` unless `-EvidenceDir` is
provided.

```powershell
.\e2e\run-local.ps1
```

Reuse an already prepared `.e2e\data\public` voice setup:

```powershell
.\e2e\run-local.ps1 -SkipSetup
```

Write artifacts to an explicit CI upload directory:

```powershell
.\e2e\run-local.ps1 -SkipSetup -EvidenceDir "$env:RUNNER_TEMP\pippal-live-ui-e2e"
```

## Safety Notes

- The runner sets `PIPPAL_E2E_LIVE=1`; direct `pytest e2e` calls skip
  unless you set this yourself.
- The test data lives under `.e2e\data\public`.
- The release-gate runner treats zero collected tests or skipped live UI tests
  as `blocked` unless `-AllowUnavailable` is passed for diagnostic CI evidence.
- The Windows integration button test temporarily writes the current
  user's Explorer context-menu registry keys, then removes them.
- Close other PipPal instances before running. The suite fails fast if
  the local command port is already owned by another process.

## Teaching Note

This is a live-desktop harness pattern. Unit tests keep logic fast and
deterministic; this manual suite proves that the real app, real widgets,
real local IPC, and real synthesis pipeline work together. Alternatives
are pure desktop automation or direct config mutation. The tradeoff is
extra test-only surface, but the run is far less flaky than tray-icon
automation and still exercises the actual user-facing app.
