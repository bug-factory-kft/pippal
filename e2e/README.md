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

```powershell
.\e2e\run-local.ps1
```

Reuse an already prepared `.e2e\data\public` voice setup:

```powershell
.\e2e\run-local.ps1 -SkipSetup
```

## Safety Notes

- The runner sets `PIPPAL_E2E_LIVE=1`; direct `pytest e2e` calls skip
  unless you set this yourself.
- The test data lives under `.e2e\data\public`.
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
