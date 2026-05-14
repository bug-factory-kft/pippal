# PipPal Privacy Policy

**TL;DR — PipPal collects nothing. The text you read with it never
leaves your machine.**

## What we collect

Nothing. PipPal is an offline-first desktop application. It has no
analytics, no telemetry, no crash reporting, no usage statistics, no
A/B framework, no cloud sync, and no remote logging.

## What stays on your machine

By default, runtime data lives under `%LOCALAPPDATA%\PipPal`:

- Configuration (`config.json`) — your preferred voice, hotkeys,
  panel options, etc.
- Recent-readings history (`history.json`) — the last ~10 selections
  you read, used to populate the tray's *Recent* submenu. Never
  uploaded.
- Downloaded Piper voices (`voices\`) — voice models installed by the
  setup script or Voice Manager.
- Temporary WAV files (`temp\`) — the audio chunks PipPal renders
  while reading. Deleted as each chunk plays.

If `PIPPAL_DATA_DIR` is set, PipPal uses that directory instead of
`%LOCALAPPDATA%\PipPal` for the same runtime files. Delete the runtime
directory and PipPal forgets that local state. The source/install
directory holds app code and, when installed by `setup.ps1`, the Piper
binary under `piper\`.

## Network access

PipPal Core makes outbound network requests in only two situations:

1. **Voice Manager / setup script** — Voice Manager downloads Piper
   voice models from `huggingface.co/rhasspy/piper-voices` when you
   click *Install*. `setup.ps1` downloads the default voice and the
   Piper binary from upstream project releases. Standard HTTPS file
   fetch; no account needed; no data sent beyond the request URL.
2. **Right-click integration helper** — sends a localhost-only
   HTTP request (`127.0.0.1:51677`) from `pippal_open.py` to the
   running PipPal instance. Never leaves your machine.

PipPal Core never contacts a server controlled by us. Paid or
third-party extensions are owned by their package and Store terms; do
not infer their behavior from this Core policy.

## Third-party software bundled or downloaded

- **Piper TTS** (MIT) — the actual TTS engine, downloaded by
  `setup.ps1` from the upstream Piper project's GitHub releases.
- **Piper voices** (per-voice licence, mostly MIT / CC-BY) — see
  [THIRD_PARTY.md](THIRD_PARTY.md).
- **Python dependencies** — listed in [THIRD_PARTY.md](THIRD_PARTY.md).
  None contact remote servers on PipPal's behalf.

If you have concerns about any of these, the source code is fully
auditable: [github.com/bug-factory-kft/pippal](https://github.com/bug-factory-kft/pippal).

## Children

PipPal is not directed at children under 13. It also doesn't collect
anything that would let us know whether a user is a child or not, so
this section is essentially redundant — but worth stating.

## Changes to this policy

If we ever start collecting anything (we don't intend to), we'll
update this document and bump the policy date below. Old versions
remain visible in the repository's git history.

---

*Last updated: 2026-05-14*
