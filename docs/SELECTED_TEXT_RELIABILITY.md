# PipPal Core - Selected-Text Reliability Evidence

Issue: [#43](https://github.com/bug-factory-kft/pippal/issues/43)

Target release branch: `release/0.2.4`

Evidence date: 2026-05-14

Worker: K

## Goal

Validate the release claim behind PipPal Core's selected-text reader:
select text in a Windows app, press the configured PipPal hotkey, and
hear that selected text locally.

This is a release-evidence artifact, not a runtime change. It records
what is already automated, what was attempted locally, and what still
needs a human or UI-automation pass before marketing copy can say the
reader works "anywhere."

## Mechanism Under Test

The Core selected-text path is clipboard based:

1. Save the current clipboard text.
2. Put a probe token on the clipboard.
3. Release the configured hotkey keys plus common modifiers.
4. Send `Ctrl+C` to the foreground app.
5. Poll the clipboard for copied selection text.
6. Restore the previous clipboard text.

The current timing constants are:

| Constant | Value | Meaning |
| --- | ---: | --- |
| `CLIPBOARD_RELEASE_GAP_S` | `0.04` | Delay after releasing hotkey modifiers before copy. |
| `CLIPBOARD_READ_DEADLINE_S` | `0.6` | Maximum wait for the foreground app to place copied text on the clipboard. |
| `CLIPBOARD_POLL_S` | `0.03` | Poll interval while waiting for clipboard change. |

This design works only when the focused app exposes selected text
through normal copy semantics. Protected documents, password fields,
custom canvases, elevated/non-elevated boundaries, remote sessions, and
apps that delay clipboard writes can legitimately fail or need separate
handling.

## Automated Validation Run

Commands run from `C:\Users\tigyi\pippal-public` on branch
`release/0.2.4`:

| Check | Result | Notes |
| --- | --- | --- |
| `python -m pytest tests\test_clipboard_capture.py tests\test_hotkey.py tests\test_command_server.py -q` | Pass: `66 passed in 19.07s` | Exact issue #43 validation command. Covers hotkey parsing/dispatch logic, clipboard capture helpers, and command-server tests. |
| `python -m pytest tests/test_clipboard_capture.py tests/test_hotkey.py tests/test_engine.py -q` | Pass: `50 passed in 0.56s` | Confirms engine capture path releases configured combo keys plus universal modifiers. |
| `python -m pytest tests/benchmarks/test_bench_hotkey.py --benchmark-only -q` | Pass: `5 passed in 3.97s` | Hotkey dispatch benchmark only; not an app compatibility benchmark. Pass-through mean was about `414 ns`; match-and-suppress mean was about `89.7 us`, well under Windows' 1 s low-level hook timeout. |
| `rg -n "pywinauto|playwright|selenium|uiautomation|keyboard.write|capture_selection|selected text|clipboard" e2e tests docs README.md pyproject.toml requirements-dev.txt` | Pass: no existing GUI automation harness found | The repo has logic and e2e infrastructure, but no app-driving selected-text compatibility harness for browsers, Office, chat apps, PDF readers, or terminals. |

## Local App Inventory

This inventory proves app binaries were discoverable locally. It does
not prove selected-text capture works in those apps.

| App category | Local app found | Version | Path |
| --- | --- | --- | --- |
| Notepad | Yes | `10.0.26100.8457` | `C:\Windows\System32\notepad.exe` |
| Edge | Yes | `148.0.3967.54` | `C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe` |
| Chrome | Yes | `148.0.7778.98` | `C:\Program Files\Google\Chrome\Application\chrome.exe` |
| Firefox | Yes | `150.0.3` | `C:\Program Files\Mozilla Firefox\firefox.exe` |
| Acrobat Reader / Acrobat | Yes | `26.1.21529.0` | `C:\Program Files\Adobe\Acrobat DC\Acrobat\Acrobat.exe` |
| Word | Yes | `16.0.19929.20136` | `C:\Program Files\Microsoft Office\root\Office16\WINWORD.EXE` |
| Outlook | Yes | `16.0.19929.20136` | `C:\Program Files\Microsoft Office\root\Office16\OUTLOOK.EXE` |
| VS Code | Yes | `1.119.0` | `C:\Users\tigyi\AppData\Local\Programs\Microsoft VS Code\Code.exe` |
| Windows Terminal | Yes | version unavailable | `C:\Users\tigyi\AppData\Local\Microsoft\WindowsApps\wt.exe` |
| Teams | Yes | version unavailable | `C:\Users\tigyi\AppData\Local\Microsoft\WindowsApps\ms-teams.exe` |
| Slack | No | n/a | n/a |
| Discord | No | n/a | n/a |

## Reliability Matrix

Legend:

- `Pass`: selected text was captured exactly enough to read.
- `Fail`: selected text was not captured, wrong text was captured, or
  clipboard restoration failed.
- `Not run`: the app exists or is expected, but this evidence pass did
  not safely drive the GUI.
- `Inconclusive`: an automation attempt failed in a way that may be a
  harness/focus problem rather than an app compatibility problem.

| App / surface | Selected text type | App version | Read path used | Result | Failure symptom / notes | Follow-up candidate |
| --- | --- | --- | --- | --- | --- | --- |
| Core harness: clipboard + hotkey + command server | Mocked selection/copy behavior | n/a | Unit tests | Pass | `66 passed in 19.07s`. Validates internal capture helper behavior, not app compatibility. | None. Keep in release gate. |
| Core harness: engine capture modifier release | Mocked selection/copy behavior | n/a | Unit tests | Pass | `50 passed in 0.56s`. Confirms configured combo keys and universal modifiers are released before copy. | None. Keep in release gate. |
| Core benchmark: hotkey dispatch | Synthetic keyboard events | n/a | `pytest-benchmark` | Pass | `5 passed in 3.97s`; dispatch is far below hook timeout. | None. Keep as performance guard, not compatibility evidence. |
| Notepad | Plain `.txt`, one sentence | `10.0.26100.8457` | Temporary file, focus window, `Ctrl+A`, then `capture_selection()` | Inconclusive / fail | Window was found (`... - Notepad`) but captured text was empty. The first PID-based attempt also failed to discover the spawned visible window. This needs manual repro or a stronger UI automation harness before calling it a product defect. | Candidate: add a reproducible Notepad selected-text smoke using WinAppDriver, pywinauto, or UI Automation, then file a product bug only if manual `Win+Shift+R` also fails. |
| Edge webpage | Web paragraph text | `148.0.3967.54` | Manual hotkey on focused page | Not run | Browser was installed, but no browser-driving selected-text harness exists in this repo. | Candidate if manual run fails: browser webpage copy delay or focus loss after hotkey. |
| Edge PDF | Selectable PDF text | `148.0.3967.54` | Manual hotkey on built-in PDF viewer | Not run | Needs PDF fixture and manual/browser automation. | Candidate if manual run fails: PDF viewer selection not copied within `0.6 s` deadline. |
| Chrome webpage | Web paragraph text | `148.0.7778.98` | Manual hotkey on focused page | Not run | Browser installed; no harness. | Candidate if manual run fails: Chrome selection copy blocked or delayed. |
| Firefox webpage | Web paragraph text | `150.0.3` | Manual hotkey on focused page | Not run | Browser installed; no harness. | Candidate if manual run fails: Firefox selection copy blocked or delayed. |
| Word / RichEdit substitute | Document paragraph text | `16.0.19929.20136` | Manual hotkey in editable document | Not run | Word installed; no Office automation run in this pass. | Candidate if manual run fails: Office selection copy requires longer deadline or focus recovery. |
| Outlook / Windows Mail substitute | Email body text | `16.0.19929.20136` | Manual hotkey in message body | Not run | Outlook installed; no mail automation run in this pass. | Candidate if manual run fails: protected/read-only message surface does not expose selection through standard copy. |
| VS Code | Editor selection | `1.119.0` | Manual hotkey in editor | Not run | VS Code installed; no Electron/editor automation run in this pass. | Candidate if manual run fails: Electron focus or clipboard delay. |
| Windows Terminal / PowerShell | Terminal buffer selection | version unavailable | Manual terminal selection | Not run | Terminal exists; terminal selections can have nonstandard copy settings, so this must be verified manually. | Candidate if manual run fails: terminal selection needs explicit copy-on-select or alternate capture path. |
| Teams / Electron chat | Chat message text | version unavailable for Teams alias | Manual hotkey in message text | Not run | Teams alias found; Slack and Discord not found. | Candidate if manual run fails: message text surface blocks normal `Ctrl+C` or exposes hidden formatting. |
| Elevated/admin app | Plain text in elevated process | n/a | Manual hotkey from normal PipPal process | Not run | Must be tested with explicit elevation boundary. Normal-process hooks/copy may not reach elevated windows. | Candidate if manual run fails: document unsupported elevation boundary or require PipPal to run at same integrity level. |

## Target Thresholds

The app-by-app matrix has 10 required compatibility categories from
issue #43. Harness-only passes do not count toward these app thresholds.

### v0.2.4 release threshold

- At least `8 / 10` required app categories pass in a manual or
  reproducible UI-automation run.
- Mandatory green rows: one browser webpage, one PDF surface, Notepad
  or Word/RichEdit, one editor/terminal surface, and one communication
  surface.
- No pass may leave the user's previous clipboard unrecovered.
- Every fail or inconclusive row must have a follow-up issue candidate
  and restrained user-facing wording.

If fewer than 8 app categories are proven, v0.2.4 can still ship only
with constrained wording such as "works with apps that support normal
copy of selected text."

### v0.2.5 reliability target

- At least `9 / 10` required app categories pass.
- The elevated/admin app row must be either green or explicitly
  documented as unsupported with a same-integrity-level explanation.
- Repeated-run reliability should be measured per app: `10 / 10`
  successful captures for simple text selections, or a documented app
  defect/follow-up.
- Add a maintained UI automation harness for at least Notepad, one
  Chromium browser, VS Code, and Windows Terminal before broadening
  claims.

## Marketing Wording Constraints

Current evidence does not justify unqualified "anywhere" or "any
program" language.

Allowed until the matrix passes:

- "Reads selected text from Windows apps that expose selection through
  normal copy/clipboard behavior."
- "Works across common Windows apps after compatibility validation."
- "If an app blocks or delays copying selected text, PipPal may report
  no text selected."

Avoid until the matrix passes:

- "Reads in any program."
- "Anywhere in Windows."
- "Browser, PDF reader, Word, terminal - anywhere."
- "Always reads selected text."
- "Universal selected-text reader."

Existing broad-claim surfaces found by `rg`:

- `README.md`: "any selected text", "any program", and "anywhere".
- `docs/ROADMAP.md`: "anywhere in Windows".
- `docs/FIRST_RUN_ACTIVATION.md`: "Try it in any app" and selected-text
  success copy. The activation flow may keep aspirational user copy,
  but release notes should not treat it as proven compatibility until
  this matrix is green.

## Follow-Up Issue Candidates

These are candidates only; no GitHub issues were opened in this pass.

| Candidate | Why |
| --- | --- |
| Add reproducible Notepad selected-text smoke | The local attempt found a Notepad window but captured empty text. Need to separate focus/harness failure from a real product failure. |
| Add browser selected-text harness for Edge or Chrome | Browser webpages are central to the product promise and cannot be covered by mocked clipboard tests alone. |
| Add PDF selected-text fixture for Edge PDF and/or Acrobat | PDF selection is a named matrix row and often differs from webpage text copy. |
| Decide elevation-boundary support policy | A normal user process may not reliably drive elevated windows; the product should state or handle that boundary. |
| Add terminal selection guidance | Windows Terminal copy behavior depends on terminal settings and selection mode. If it fails, docs should explain the expected copy setting or fallback. |

## Release Decision

For issue #43, the repo-side logic gate is green, but broad
app-compatibility evidence is not complete. This document should be
treated as a structured validation matrix and a release wording guard.
Do not claim "anywhere" for Core v0.2.4 unless the manual/common-app
matrix is completed and meets the threshold above.

