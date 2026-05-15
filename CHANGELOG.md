# PipPal Changelog

## 0.2.4 - 2026-05-15

Release date: 2026-05-15

Categories:

- Onboarding: added a first-run activation panel that guides a new user
  from setup to a real sample playback before setup can be completed.
- Voice setup: the first-run Voice Manager path opens on the recommended
  Ryan voice, returns to the activation panel after install, and keeps the
  voice list scrollable over row content.
- UI consistency: Settings-adjacent dialogs now use the shared native
  Windows title bar, dark dialog body, and centered placement instead of
  custom internal headers or top-left fallback placement.
- Selected text reliability: improved the Notepad selected-text capture
  path and documented the current compatibility evidence without broad
  "anywhere" claims.
- Safety and release gates: production command-server control routes stay
  hidden unless the explicit E2E harness enables them, and live UI evidence
  capture is now part of the release-readiness story.

## 0.2.3 - 2026-05-13

Release date: 2026-05-13

Categories:

- Reliability: fixed atomic single-instance startup, isolated playback
  temporary chunks per session, and improved settings-window reopen
  behavior.
- UI consistency: added the core open-source notices viewer to Settings
  and stabilized chromeless dialog placement and dragging.
- Voice readiness: validates configured Piper voice files before use,
  encodes Voice Manager download URLs, and caps unbroken text chunks.
- Hotkeys and launch surface: rejects duplicate hotkey combinations,
  fixes context-menu helper import paths, portable launchers, package
  asset runtime paths, and setup default voice paths.
- Recent history: command-server and file-open read requests now appear
  in the Recent tray menu after successful playback starts.
- QA: adds install-surface smoke coverage and regression tests for the
  release-critical startup, voice, context-menu, playback, settings,
  and launcher paths.

## 0.2.0 - Public release

Release date: 2026-05-11

- Released the public PipPal core as the open-source Community edition.
- Included the reader panel, Windows tray app, settings UI, hotkeys,
  Piper voice support, and local smoke/test coverage.
- Kept paid-edition features out of the public package; Store builds
  are maintained separately.
