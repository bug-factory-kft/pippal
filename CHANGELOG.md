# PipPal Changelog

## 0.2.2 - 2026-05-12

Release date: 2026-05-12

Categories:

- Reliability: fixed atomic single-instance startup, isolated playback
  temporary chunks per session, and improved settings-window reopen
  behavior.
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
