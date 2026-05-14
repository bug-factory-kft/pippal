# PipPal Core - Trust and Positioning Proof

Issue: [#60](https://github.com/bug-factory-kft/pippal/issues/60)

Evidence date: 2026-05-14

Scope: public/free PipPal Core only. PipPal Pro is a separate paid
Microsoft Store build with proprietary extension code and its own Store
terms.

This page is a factual buyer/user-facing proof surface. It intentionally
does not compare PipPal against named competitors; dated competitor
evidence belongs in the separate issue #59 artifact when available.

## Factual Core Positioning

PipPal Core is a Windows tray app that reads selected text aloud using a
local Piper TTS engine. It is strongest for Windows apps that expose
selected text through normal copy/clipboard behavior. Reading and
playback do not require a Bug Factory account, API key, telemetry
service, or cloud TTS service.

Recommended short wording:

> PipPal Core reads selected text from Windows apps that expose selection
> through normal copy behavior, using local Piper speech on your PC.

Do not shorten this to "works anywhere" or "reads in any program" until
the selected-text reliability matrix supports that claim.

## Proof Surfaces

| User-facing statement | Current proof source | Boundary |
| --- | --- | --- |
| Core has no analytics, telemetry, crash reporting, cloud sync, or remote logging. | [PRIVACY.md](PRIVACY.md) | Applies to this public Core package. Paid or third-party extensions are separate packages with their own terms. |
| Selected text, recent history, config, downloaded voices, and temporary WAV files stay on the user's machine. | [PRIVACY.md](PRIVACY.md) | Voice downloads still contact upstream file hosts when the user installs voices. |
| Core reading is local-first after the local Piper engine and voice assets are present. | [PRIVACY.md](PRIVACY.md), [THIRD_PARTY.md](THIRD_PARTY.md) | Initial setup can download Piper and voice files from upstream sources. |
| First-run activation is a Core flow, not a Pro upsell or account gate. | [FIRST_RUN_ACTIVATION.md](FIRST_RUN_ACTIVATION.md) | The document is a design and acceptance artifact for `release/0.2.4`; implementation status should be checked from the issue/branch. |
| Live Windows UI readiness is release-gated with reviewable evidence. | [LIVE_UI_E2E_RELEASE_GATE.md](LIVE_UI_E2E_RELEASE_GATE.md) | The gate requires a Windows desktop session and local Piper assets. |
| Selected-text compatibility is constrained by copy/clipboard behavior. | [SELECTED_TEXT_RELIABILITY.md](SELECTED_TEXT_RELIABILITY.md) | Protected documents, password fields, custom canvases, elevated app boundaries, remote sessions, or slow clipboard writes may need separate handling. |

## Local And Offline Boundary

By default, Core runtime data lives under `%LOCALAPPDATA%\PipPal`; if
`PIPPAL_DATA_DIR` is set, Core uses that directory instead. The data
surface is:

- `config.json` for local settings such as voice, hotkeys, and panel
  options.
- `history.json` for the recent-readings menu.
- `voices\` for downloaded Piper voice models.
- `temp\` for temporary WAV chunks rendered during playback and deleted
  as chunks play.

Core's documented outbound network use is limited to setup/Voice Manager
downloads for Piper and voice files, plus a localhost-only request from
the Explorer helper to the running PipPal instance. Core does not send
selected text, reading history, config, or generated WAV files to a Bug
Factory server.

## What Core Does Not Do

- Core does not require an account, API key, telemetry opt-in, cloud TTS,
  or Pro activation before local reading.
- Core does not guarantee selected-text capture in every Windows surface.
  It depends on the focused app exposing selected text through normal
  copy/clipboard behavior.
- Core does not include the proprietary Pro extension package, Pro Store
  licence, or Pro-only behavior.
- Core does not make medical, legal, accessibility-compliance,
  educational-outcome, productivity, or "best/safest/most private"
  claims. Any such claim needs human/legal review before use.

## Choose PipPal Core If

- You want a free, auditable Windows desktop reader that speaks selected
  text locally.
- You prefer local Piper voices over cloud TTS services for everyday
  reading.
- You are comfortable with a selected-text workflow based on normal
  copy/clipboard behavior.
- You want the Core feature set: tray app, global hotkeys, floating
  reader panel, local Voice Manager, recent readings, `.txt`/`.md`
  right-click integration, and the public plugin host.

## Choose Another Tool If

- You need macOS, Linux, mobile, browser-only, or managed enterprise
  deployment today.
- You need account sync, web dashboards, cloud voices, voice cloning, or
  server-side document libraries in the free app.
- You need guaranteed capture from protected PDFs, password fields,
  custom canvas apps, elevated windows, remote sessions, or apps that do
  not expose selected text through copy.
- You need vendor-backed compliance, legal, medical, education, or
  accessibility guarantees beyond the Core privacy policy and MIT
  licence.

## Pro Upgrade Path

Core is meant to be usable on its own. Pro is discoverable as a paid
Microsoft Store path for users who want Store-distributed convenience
features, but Pro is not required for Core activation, local Piper
reading, the floating reader panel, the right-click helper, or the
public plugin host.

For current Pro availability, pricing, and feature details, use the
Microsoft Store listing or the Bug Factory product site rather than this
public Core repo. The public licence and package boundary are documented
in [TERMS.md](TERMS.md).

## Claims Requiring Human Or Legal Review

- Any named competitor comparison, superiority claim, or market category
  claim. Wait for issue #59 evidence and human marketing review.
- Any "works anywhere", "reads in any program", or "universal selected
  text reader" claim until the selected-text matrix supports it.
- Any Pro pricing, refund, Store entitlement, or proprietary feature
  claim not copied from the current Store/product surface.
- Any compliance, security certification, accessibility conformance,
  medical, legal, education, or productivity-outcome claim.

## Learning Note

This page uses proof-backed positioning: a short user promise linked to
specific evidence docs. The pattern keeps marketing copy close to tested
release gates and privacy boundaries. It was chosen over a competitor
matrix because issue #59 owns that evidence. Alternatives are a full
comparison page or a terse FAQ; the tradeoff is more conservative copy,
but fewer unsupported claims.
