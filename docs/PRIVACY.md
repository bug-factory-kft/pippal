# PipPal Privacy Policy

**TL;DR — PipPal collects nothing. The text you read with it never
leaves your machine.**

## What we collect

Nothing. PipPal is an offline-first desktop application. It has no
analytics, no telemetry, no crash reporting, no usage statistics, no
A/B framework, no cloud sync, and no remote logging.

## What stays on your machine

- Configuration (`config.json`) — your preferred voice, hotkeys,
  panel options, etc.
- Recent-readings history (`history.json`) — the last ~10 selections
  you read, used to populate the tray's *Recent* submenu. Never
  uploaded.
- Temporary WAV files (`temp/`) — the audio chunks PipPal renders
  while reading. Deleted as each chunk plays.

All three live under your PipPal install directory and are visible
to you. Delete them and PipPal forgets.

## Network access

PipPal makes outbound network requests in only three situations:

1. **Voice Manager / setup script** — downloads Piper voice models
   from `huggingface.co/rhasspy/piper-voices` when you click
   *Install*. Standard HTTPS file fetch; no account needed; no data
   sent beyond the request URL.
2. **Right-click integration helper** — sends a localhost-only
   HTTP request (`127.0.0.1:51677`) from `pippal_open.py` to the
   running PipPal instance. Never leaves your machine.
3. *(Microsoft Store edition only)* **Local Ollama** — AI actions like
   Summary / Translate are dispatched to a locally-running Ollama
   daemon at `http://localhost:11434`. Local-only.

PipPal never contacts a server controlled by us.

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

*Last updated: 2026-05-03*
