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

## Common-App Matrix Contract

Every compatibility row should answer four practical questions:

1. What exact surface had focus?
2. What text was selected, and how was it selected?
3. What should normal `Ctrl+C` copy from that surface?
4. If capture fails, is the blocker an app limitation, a focus/automation
   problem, a timing problem, an integrity-level boundary, or a PipPal bug?

Expected semantics and blocker handling for the release matrix:

| Surface category | Fixture to use | Expected copy semantics | Blocker handling |
| --- | --- | --- | --- |
| Notepad / plain text | Temporary `.txt` with one unique sentence | `Ctrl+C` copies exactly the selected sentence as plain text. | If normal `Ctrl+C` works but PipPal captures empty text, treat as a Core capture bug. If normal copy fails, record the app/selection setup as invalid. |
| Browser webpage | Local HTML page or stable webpage paragraph | `Ctrl+C` copies the visible selected paragraph text, ignoring hidden markup. | If capture fails, first separate focus/selection loss from browser copy delay. Repeat with Edge and one non-Edge browser before generalizing. |
| Browser PDF viewer | Local selectable PDF fixture in Edge/Chrome | `Ctrl+C` copies selected PDF text in reading order. | If empty or delayed, record whether the PDF text is selectable outside PipPal and whether the `0.6 s` deadline is too short. |
| Dedicated PDF reader | Local selectable PDF fixture in Acrobat or equivalent | `Ctrl+C` copies selected PDF text without OCR-only assumptions. | If normal copy fails, classify as document/app protection. If normal copy works but PipPal fails, open an app-specific capture issue. |
| Editor / IDE | VS Code or similar editor with one selected line | `Ctrl+C` copies exact selected editor text, preserving line breaks. | If capture fails, check Electron focus and clipboard latency before changing Core behavior. |
| Office/RichEdit app | Word, WordPad/RichEdit substitute, or editable email draft | `Ctrl+C` copies selected rich text as usable plain text for TTS. | If formatting or hidden text leaks into the clipboard text, document normalization expectations separately from capture reliability. |
| Terminal | Windows Terminal or console selected buffer text | `Ctrl+C` copies the highlighted buffer text according to terminal settings. | Treat copy-on-select and terminal shortcut settings as part of the fixture; do not call this green without recording them. |
| Communication app | Teams, Slack, Discord, Outlook message body, or webmail | `Ctrl+C` copies user-visible selected message text. | If the surface blocks selection/copy, document it as unsupported or needs app-specific guidance; do not convert it into a broad product claim. |
| Elevated/admin app | Plain selected text in an elevated process | Same-integrity `Ctrl+C` copies selected text; normal PipPal may not reach elevated windows. | If normal-process PipPal cannot drive the app, classify the integrity-level boundary explicitly instead of treating it as a generic failure. |

## Automated Validation Run

Commands run from `C:\Users\tigyi\pippal-public` on branch
`release/0.2.4`:

| Check | Result | Notes |
| --- | --- | --- |
| `python -m pytest tests\test_clipboard_capture.py tests\test_hotkey.py tests\test_command_server.py -q` | Pass: `66 passed in 19.07s` | Exact issue #43 validation command. Covers hotkey parsing/dispatch logic, clipboard capture helpers, and command-server tests. |
| `python -m pytest tests\test_clipboard_capture.py tests\test_hotkey.py -q` | Pass: `31 passed in 0.53s` | Exact issue #57 validation command. Confirms the pure logic gate is still green while the Notepad repro below exercises real Windows copy behavior. |
| `python -m pytest tests/test_clipboard_capture.py tests/test_hotkey.py tests/test_engine.py -q` | Pass: `50 passed in 0.56s` | Confirms engine capture path releases configured combo keys plus universal modifiers. |
| `python -m pytest tests/benchmarks/test_bench_hotkey.py --benchmark-only -q` | Pass: `5 passed in 3.97s` | Hotkey dispatch benchmark only; not an app compatibility benchmark. Pass-through mean was about `414 ns`; match-and-suppress mean was about `89.7 us`, well under Windows' 1 s low-level hook timeout. |
| `rg -n "pywinauto|playwright|selenium|uiautomation|keyboard.write|capture_selection|selected text|clipboard" e2e tests docs README.md pyproject.toml requirements-dev.txt` | Pass: no existing GUI automation harness found | The repo has logic and e2e infrastructure, but no app-driving selected-text compatibility harness for browsers, Office, chat apps, PDF readers, or terminals. |

## Issue #57 Notepad Repro

Worker P ran this on `release/0.2.4` on 2026-05-14.

Environment:

- Windows: Microsoft Windows 11 Pro `10.0.26100`, build `26100`, 64-bit.
- Notepad: `C:\WINDOWS\System32\notepad.exe`,
  product version `10.0.26100.8457`, file version
  `10.0.26100.8457 (WinBuild.160101.0800)`.
- Source Python used for the repro: `C:\Python314\python.exe`.
- A live installed `PipPal` process was present at
  `C:\Program Files\WindowsApps\BugFactory.pippal-pro_0.2.2.0_x64__km6tvv8cv49he\PipPal.exe`.
  The release-branch hotkey was therefore not tested through the installed
  app; the source capture helper and local hotkey-manager harness were tested
  directly.

Test text:

```text
PipPal issue 57 Notepad selected-text repro: Ctrl+C should copy this exact sentence.
```

Manual/UI repro steps and results:

| Step | Command / action | Result |
| --- | --- | --- |
| Open focused Notepad fixture | Start `notepad.exe` with a temporary `.txt` file under `C:\WINDOWS\TEMP`, wait for `pippal_issue57_notepad_*.txt - Notepad`, then activate that title with `WScript.Shell.AppActivate`. | Pass. Example focused title: `pippal_issue57_notepad_sendkeys.txt - Notepad`; `AppActivate` returned `true`. |
| Select text | Send `Ctrl+A` to Notepad with `[System.Windows.Forms.SendKeys]::SendWait('^a')`. | Pass enough for copy validation. |
| Verify `Ctrl+C` outside PipPal | Set clipboard to `ISSUE57_SENDKEYS_SENTINEL`, send `[System.Windows.Forms.SendKeys]::SendWait('^c')`, then read `Get-Clipboard -Raw`. | Pass. Clipboard became the exact test text above. This proves Notepad exposes the selected text through normal copy semantics on this machine. |
| Isolate the keyboard library copy path | With the same Notepad selection active, set clipboard to `ISSUE57_KEYBOARD_COPY_SENTINEL`, focus Notepad with `SetForegroundWindow`, then run `keyboard.press_and_release("ctrl+c")` from Python. | Fail. Clipboard stayed `ISSUE57_KEYBOARD_COPY_SENTINEL` for the 2 s polling window. |
| Test PipPal source capture helper | With the same Notepad selection active, set previous clipboard to `ISSUE57_HYBRID_PREVIOUS_CLIPBOARD`, then call `pippal.clipboard_capture.capture_selection(DummyEngine(), "windows+shift+r")`. | Fail. `captured_text` was empty, `error` was `null`, and `clipboard_after_capture` was restored to `ISSUE57_HYBRID_PREVIOUS_CLIPBOARD`. |
| Test local hotkey-manager dispatch harness | Register `HotkeyManager().register("windows+shift+r", handler)`, focus Notepad, then inject `keyboard.press_and_release("windows+shift+r")`. | Inconclusive. The handler was not called within 3 s. This does not prove the live human hotkey path because injected Win-key events and the already-running installed PipPal may affect the harness. |

Conclusion:

Notepad copy itself works outside PipPal, but the current source capture
path fails before clipboard timing becomes relevant: the `keyboard` library
copy injection did not deliver `Ctrl+C` to modern Notepad in this repro,
so `capture_selection()` correctly restored the prior clipboard but returned
empty selected text.

Follow-up bug recommendation:

Open a focused Core bug for Notepad selected-text capture failure with this
expected behavior: when focused Notepad has selected text that normal `Ctrl+C`
can copy, PipPal's read-selection path should capture the same text or surface
a clear recoverable failure without disturbing the user's clipboard. The likely
fix area is the copy-injection strategy inside `pippal.clipboard_capture`, not
the clipboard polling deadline.

## Issue #58 Notepad Fix Smoke

Worker S ran this on `release/0.2.4` on 2026-05-14 after the
`clipboard_capture` modifier-release fix.

Manual/UI smoke shape:

1. Open a temporary `.txt` fixture in Notepad.
2. Focus Notepad with `WScript.Shell.AppActivate`.
3. Select all text with `[System.Windows.Forms.SendKeys]::SendWait('^a')`.
4. Set the previous clipboard to `ISSUE58_PATCHED_PREVIOUS_CLIPBOARD`.
5. Run source `pippal.clipboard_capture.capture_selection(...)` with
   `PYTHONPATH=C:\Users\tigyi\pippal-public\src` and hotkey combo
   `windows+shift+r`.

Result:

```json
{
  "captured_text": "PipPal issue 58 patched Notepad smoke: capture_selection should copy this exact sentence.",
  "clipboard_after_capture": "ISSUE58_PATCHED_PREVIOUS_CLIPBOARD"
}
```

Conclusion: the source capture helper now copies selected Notepad text
in this local smoke while still restoring the previous clipboard. The
remaining gap is a maintained automated UI smoke and a live installed-app
human-hotkey confirmation.

## Issue #62 Maintained Notepad and Edge UI Smokes

Issue: [#62](https://github.com/bug-factory-kft/pippal/issues/62)

Target release branch: `release/0.2.5`

What it adds:

- `tests/ui_smokes/test_selected_text_smokes.py` drives Notepad and
  Edge directly and asserts that
  `pippal.clipboard_capture.capture_selection` captured the exact
  selected text *and* restored the previous clipboard.
- `e2e/run-ui-smokes.ps1` is the maintained runner. It writes a
  `ui-smokes-summary.json`, a per-smoke `<smoke_id>.json` evidence
  file (app version, fixture path, captured text, clipboard
  restoration), `pytest-ui-smokes.junit.xml`, and `pytest-ui-smokes.log`
  under `.e2e\evidence\ui-smokes-<UTC timestamp>\`.

Surfaces covered today:

- Notepad happy path: temp `.txt` fixture, `WScript.Shell.AppActivate`
  focus, `SendKeys ^a` selection, then `capture_selection`.
- Notepad known-bad-state recovery: same fixture, collapsed selection
  (`{END}{HOME}`), then `capture_selection`. Asserts empty result and
  that the clipboard sentinel survives.
- Edge webpage happy path: local HTML fixture that DOM-selects a
  paragraph on `window.load`, throwaway `--user-data-dir`,
  `AppActivate` focus, then `capture_selection`.

Gating:

- `python -m pytest` does NOT run the UI smokes by default (the dir is
  in `addopts --ignore=tests/ui_smokes`).
- `tests/ui_smokes/conftest.py` skips when `platform.system() != 'Windows'`
  or `PIPPAL_UI_SMOKES != '1'`.
- `e2e/run-ui-smokes.ps1` sets `PIPPAL_UI_SMOKES=1` and treats a
  zero-test / all-skipped run as `blocked` unless `-AllowUnavailable`
  is explicitly passed (matches `e2e/run-local.ps1`).

Out of scope for #62 and tracked elsewhere:

- PDF surfaces (#63).
- Editor / terminal / chat surfaces (#61).
- Live installed-app human-hotkey confirmation (`e2e/run-local.ps1`
  release gate, #42).

## Issue #63 PDF Selected-Text Smokes

Issue: [#63](https://github.com/bug-factory-kft/pippal/issues/63)

Target release branch: `release/0.2.5`

What it adds:

- `tests/ui_smokes/test_pdf_smokes.py` extends the maintained UI smoke
  harness to PDF surfaces: Edge's built-in PDF viewer with a
  selectable-text fixture, Edge's built-in PDF viewer with an
  image-only fixture (no text content layer), and Acrobat / Adobe
  Reader with the same selectable-text fixture (or a structured
  `blocked` / `unavailable` outcome when Acrobat is absent or
  unhealthy on the gate machine).
- PDF fixtures are synthesised at test time via `pypdf` (Helvetica
  Type 1 font + hand-stitched `BT ... Tj ... ET` content stream).
  No binary PDFs are checked into the repo. This matches the issue
  #62 strategy that avoids checked-in fixture binaries.
- The Edge PDF viewer runs in `--inprivate` mode with `--disable-sync`
  so an already-signed-in Edge profile cannot inject a sync infobar
  that intercepts focus before `Ctrl+A` reaches the PDF.js iframe.

Surfaces covered today:

| Smoke | Surface | What it asserts |
| --- | --- | --- |
| `test_edge_pdf_selected_text_happy_path` | Edge built-in PDF viewer, selectable text | After `Ctrl+A` in the document iframe, `capture_selection` returns the exact fixture body (after line-ending normalisation) AND restores the previous clipboard sentinel. |
| `test_edge_pdf_image_only_records_unsupported` | Edge built-in PDF viewer, no text content layer | `capture_selection` returns the empty string AND the previous clipboard sentinel is preserved. A non-empty result here would catch a future viewer change that started returning OCR-derived text — the matrix and contract would then need to be revisited together. |
| `test_acrobat_pdf_selected_text_or_blocked` | Acrobat / Adobe Reader, selectable text | If Acrobat is installed and reaches a titled document window, the same exact-capture / clipboard-restoration contract as the Edge happy path. If Acrobat is absent, `pytest.skip` with a structured evidence file naming the searched paths; the runner then reports `unavailable` (with `-AllowUnavailable`) or `blocked` (without). If Acrobat is present but stuck on a sign-in / EULA modal that prevents the document window from being titled, the smoke records the same `blocked` outcome with `failure_symptom` and `candidate_fix` fields. |

Focus mechanism delta vs. issue #62:

The original `WScript.Shell.AppActivate` focus primitive is too fuzzy
for PDF smokes — its title matching is substring-based but does not
require a unique match, so on a gate machine with many similarly
titled windows it can latch onto the wrong window while still
reporting success. PDF smokes need exact targeting because driving
`Ctrl+A` into the wrong window would silently corrupt the user's
clipboard. `tests/ui_smokes/_harness.py` now exposes
`activate_window_by_exact_title_substring`, which uses
`Get-Process` + `SetForegroundWindow` with an Alt-key
foreground-lock bypass and then verifies `GetForegroundWindow`
matches the target handle. The legacy
`activate_window_by_title_fragment` now delegates to this primitive.

Key-injection delta vs. issue #62:

Edge's built-in PDF viewer is a Chromium PDF.js iframe and does not
pick up `^a` / `^c` from
`System.Windows.Forms.SendKeys.SendWait`, even when the document
iframe has the foreground. PDF smokes use the `keyboard` Python lib
(HID-level injection) via `send_hotkey_via_keyboard_lib` for the
selection-driving Ctrl+A; SendKeys remains the default for non-PDF
surfaces.

Gate-machine 5-cold-run results (2026-05-15, Worker C):

Environment:

- Windows: Microsoft Windows 11 Pro `10.0.26100`.
- Python: `3.14.0`.
- Edge: `C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe`,
  product version `148.0.3967.54`.
- Acrobat: `C:\Program Files\Adobe\Acrobat DC\Acrobat\Acrobat.exe`,
  product version `26.1.21529.0`. Installed but the document window
  never published a title across 5 cold runs — likely a stuck sign-in
  / EULA modal on this gate machine. Recorded as `blocked` with a
  structured `candidate_fix` ("manually launch Acrobat once on the
  gate machine, dismiss any sign-in / update prompt, then re-run").

| Smoke | Run 1 | Run 2 | Run 3 | Run 4 | Run 5 |
| --- | --- | --- | --- | --- | --- |
| `test_edge_pdf_selected_text_happy_path` | pass | pass | pass | pass | pass |
| `test_edge_pdf_image_only_records_unsupported` | pass | pass | pass | pass | pass |
| `test_acrobat_pdf_selected_text_or_blocked` | blocked | blocked | blocked | blocked | blocked |
| Existing #62 smokes (Notepad happy + recovery, Edge webpage) | pass | pass | pass | pass | pass |

Edge PDF happy-path reliability: **5 / 5** cold runs green
(threshold: ≥ 4 / 5, matching the #62 bar). Acrobat outcome stable
across runs (always `blocked` on this gate machine).

Unsupported PDF surfaces (until OCR work lands):

The image-only smoke documents the current contract: PDFs with no
text content layer (scanned documents, image-only exports,
camera-captured PDFs) produce an empty capture. The clipboard
sentinel is preserved, so PipPal does not destroy the user's
clipboard when the foreground PDF has no selectable text. Protected
PDFs that restrict text extraction are expected to behave the same
way and are likewise unsupported until OCR work lands.

OCR is out of scope for issue #63. The reliability matrix may grow
an OCR-fed row once a Core OCR ticket lands; the open-question
direction is tracked separately under the broader compatibility
roadmap. The image-only smoke is the regression guard that prevents
a viewer change from silently broadening the supported surface
before OCR is implemented and validated.

## Issue #43 Edge Browser Smoke

Worker AE ran this on `release/0.2.4` on 2026-05-14.

Environment:

- Edge:
  `C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe`,
  product version `148.0.3967.54`.
- Temporary fixture:
  `C:\WINDOWS\TEMP\pippal_issue43_edge_20260514_220108\edge-selected-text-smoke.html`.
- Source helper path:
  `PYTHONPATH=C:\Users\tigyi\pippal-public\src`.

Test text:

```text
PipPal issue 43 Edge browser selected-text smoke: Ctrl+C should copy this exact browser sentence.
```

Manual/UI smoke shape:

1. Create a local HTML page with one paragraph containing the test text.
2. On page load, select that paragraph with `window.getSelection()` and a
   DOM range.
3. Launch Edge with a temporary profile and the local fixture.
4. Focus the Edge window titled `PipPal Issue 43 Browser Smoke - Profile 1 - Microsoft Edge`.
5. Set the previous clipboard to `ISSUE43_EDGE_PREVIOUS_CLIPBOARD`.
6. Run source `pippal.clipboard_capture.capture_selection(...)` with hotkey
   combo `windows+shift+r`.

Result:

```json
{
  "expected_text": "PipPal issue 43 Edge browser selected-text smoke: Ctrl+C should copy this exact browser sentence.",
  "captured_text": "PipPal issue 43 Edge browser selected-text smoke: Ctrl+C should copy this exact browser sentence.",
  "matched_expected": true,
  "clipboard_after_capture": "ISSUE43_EDGE_PREVIOUS_CLIPBOARD",
  "clipboard_restored": true
}
```

Conclusion: the source capture helper copied a selected Edge webpage
paragraph exactly and restored the previous clipboard. This proves one
browser-webpage row for the source helper, not all browser surfaces. It
does not cover Chrome, Firefox, complex web apps, browser PDF viewers,
or the live installed-app human-hotkey path.

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
| Notepad | Plain `.txt`, one sentence | `10.0.26100.8457` | Manual/UI repro: Windows Forms `Ctrl+A` selection, then source `capture_selection()` | Pass for source capture helper | Issue #57 established that normal Notepad copy worked while the old source capture path failed. Issue #58 fixed the pre-copy modifier release path; the patched smoke captured the exact selected sentence and restored `ISSUE58_PATCHED_PREVIOUS_CLIPBOARD`. The live installed-app human hotkey still needs confirmation because the old injected `Win+Shift+R` hotkey-manager harness was inconclusive. | Add a maintained reproducible Notepad selected-text smoke using WinAppDriver, pywinauto, or UI Automation; run a live installed-app human-hotkey confirmation. |
| Edge webpage | Local HTML paragraph selected with DOM range | `148.0.3967.54` | Manual/UI smoke with temporary Edge profile, focused page, then source `capture_selection()` | Pass for source capture helper | Worker AE's issue #43 smoke captured the exact selected sentence and restored `ISSUE43_EDGE_PREVIOUS_CLIPBOARD`. This proves one simple Edge webpage paragraph, not browser PDFs, complex web apps, Chrome, Firefox, or the live installed-app human hotkey. | Add maintained browser automation; repeat in Chrome or Firefox; run live installed-app human-hotkey confirmation. |
| Edge PDF | Selectable PDF text (issue #63) | `148.0.3967.54` | Maintained `tests/ui_smokes/test_pdf_smokes.py::test_edge_pdf_selected_text_happy_path` via `e2e/run-ui-smokes.ps1` | Pass for source capture helper | 5 / 5 cold runs green on the gate machine. PDF fixture synthesised in-test via `pypdf`. The Edge built-in PDF viewer needs HID-level Ctrl+A injection (`keyboard.send`) instead of `SendKeys` because the PDF.js iframe ignores `^a` from the SendKeys path. | None for now. Keep in release gate. |
| Edge PDF (image-only) | PDF with no text content layer (issue #63) | `148.0.3967.54` | Maintained `tests/ui_smokes/test_pdf_smokes.py::test_edge_pdf_image_only_records_unsupported` | Pass for empty-capture contract | 5 / 5 cold runs green. Image-only / scanned PDFs return empty captured text and preserve the previous clipboard. Marketing copy must not imply PipPal can read scanned PDFs until OCR work lands. | Open Core OCR ticket to broaden coverage; until then this row is the "unsupported" guard. |
| Acrobat / Adobe Reader | Selectable PDF text (issue #63) | `26.1.21529.0` | Maintained `tests/ui_smokes/test_pdf_smokes.py::test_acrobat_pdf_selected_text_or_blocked` | Blocked on the 2026-05-15 gate machine | Acrobat is installed but its document window never published a title across 5 cold runs — likely a stuck sign-in / EULA modal that the smoke cannot dismiss without UI Automation. The smoke records `blocked` with structured `failure_symptom` and `candidate_fix` evidence; `e2e/run-ui-smokes.ps1 -AllowUnavailable` promotes this to `unavailable`. | Manually launch Acrobat once on the gate machine, dismiss any sign-in / update prompt, then re-run the gate. If the prompt cannot be dismissed, file a follow-up issue per `docs/RELEASE_CHECKLIST.md` waiver policy. |
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

Current 2026-05-14 status after Worker AE: two app categories have direct
source-helper smoke evidence, Notepad and Edge webpage. This is still below
the v0.2.4 threshold and still does not justify broad "anywhere" wording.

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

Original broad-claim surfaces found by the 2026-05-14 `rg` scan:

- `README.md`: "any selected text", "any program", and "anywhere".
- `docs/ROADMAP.md`: "anywhere in Windows".
- `docs/FIRST_RUN_ACTIVATION.md`: "Try it in any app" and selected-text
  success copy.

These entries are retained as wording-guard context. Future public copy
should stay within the allowed wording above unless this matrix becomes
green enough to support broader compatibility claims.

## Follow-Up Issue Candidates

These are candidates only; no GitHub issues were opened in this pass.

| Candidate | Why |
| --- | --- |
| Add Notepad source and live-hotkey UI smokes | Issue #58 fixed the source helper's Notepad capture path locally, but the repo still needs maintained UI automation plus a live installed-app human-hotkey confirmation before this row is release-grade. |
| Promote the Edge webpage smoke into a maintained browser selected-text harness | Worker AE proved one simple Edge paragraph through the source helper, but browser webpages are central to the product promise and still need repeatable automation plus Chrome/Firefox coverage. |
| Add PDF selected-text fixture for Edge PDF and/or Acrobat | PDF selection is a named matrix row and often differs from webpage text copy. |
| Decide elevation-boundary support policy | A normal user process may not reliably drive elevated windows; the product should state or handle that boundary. |
| Add terminal selection guidance | Windows Terminal copy behavior depends on terminal settings and selection mode. If it fails, docs should explain the expected copy setting or fallback. |

## Release Decision

For issue #43, the repo-side logic gate is green, and Notepad plus one
Edge webpage source-helper smoke are now proven. Broad app-compatibility
evidence is still incomplete. This document should be treated as a
structured validation matrix and a release wording guard. Do not claim
"anywhere" for Core v0.2.4 unless the manual/common-app matrix is
completed and meets the threshold above.
