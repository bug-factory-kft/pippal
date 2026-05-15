# PipPal Core UI Fit QA

Issue: #45, "Polish reader panel and Settings visual fit with small-screen QA matrix"
Branch: `release/0.2.4`
Worker: L
Date: 2026-05-14

## Scope

This pass covered the public Core Settings window and reader panel only.
The harness forced the Settings window to its minimum stress size
(`560x600`) and used Tk scaling values equivalent to common Windows
100%, 125%, and 150% display scaling:

- 100%: `tk scaling 1.333`
- 125%: `tk scaling 1.667`
- 150%: `tk scaling 2.000`

The OS display setting was not changed. This avoids disrupting the live
desktop session and gives deterministic widget metrics, but final
release QA should still include manual screenshots on real Windows
125% and 150% display scaling.

## Scaling Matrix

| Scale | Settings result | Reader panel result | Outcome |
| --- | --- | --- | --- |
| 100% | Scrollable body is usable at `560x600`. Before fix, `Karaoke offset` helper text exceeded the row by 35 px. After fix, no row overflow remained in the measured Reader panel card/footer controls. | Fixed 760 px panel rendered a 2-line sample at 132 px height. Header action label and body text fit. | Pass after fix. |
| 125% | Scrollable body is usable at `560x600`. Before fix, `Karaoke offset` helper text exceeded the row by 122 px. After fix, measured card/footer rows fit. | Fixed 760 px panel rendered a 2-line sample at 132 px height. Header action label and body text fit. | Pass after fix. |
| 150% | Scrollable body is usable at `560x600`. Before fix, footer action buttons clipped (`Cancel` was visibly truncated) and `Karaoke offset` exceeded the row by 208 px. After fix, footer buttons stack safely and the helper label wraps. | Fixed 760 px panel rendered a 2-line sample at 132 px height. Header action label and body text fit. | Pass with noted Voice-row risk. |

## Fixes Applied

- `src/pippal/ui/settings_window.py`: Settings footer now switches to a
  stacked Reset/action layout when the total button request width exceeds
  the available footer width. This keeps Save, Apply, Cancel, and Reset
  readable at 150% scaling and minimum width.
- `src/pippal/ui/settings_cards.py`: Reader panel spinbox unit labels now
  wrap and expand inside the row, which keeps the long karaoke timing
  explanation visible instead of overflowing.

## Remaining Risks

- The Voice row is still tight at 150% and `560x600`: `Manage...` measured
  5 px wider than the available row in the Core-only harness. It was not
  patched here because the safer fix is a responsive Voice-row layout, not
  another narrow copy tweak.
- The first-run/no-voice state uses `Install voices...`, which is longer
  than `Manage...`; that state needs a dedicated high-DPI screenshot pass.
- About/notices explanatory labels report slightly larger requested widths
  than actual widths, but they are wrapped labels and remained readable in
  this pass.
- The reader panel remains a fixed 760 px wide. It fit the sampled Core
  text and action label, but very narrow screens or extension-provided
  action labels should be covered by a separate responsive overlay issue.
- Live E2E could not run in this pass because `127.0.0.1:51677` was already
  owned by the installed Pro app:
  `C:\Program Files\WindowsApps\BugFactory.pippal-pro_0.2.2.0_x64__km6tvv8cv49he\PipPal.exe`
  (PID 12620). The harness requires closing running PipPal instances first.

## Follow-up Implementation Issues

1. Make the Voice row responsive at high DPI.
   - Stack or wrap the Manage/Install button below the voice combobox when
     the row is narrower than its requested width.
   - Include the no-installed-voice state in the acceptance screenshots.

2. Add a deterministic UI-fit smoke harness.
   - Keep extension discovery disabled inside the test harness only.
   - Assert Settings footer buttons, Reader panel spinbox rows, and
     Voice-row controls at 100%, 125%, and 150% Tk scaling.
   - Store metrics as text artifacts; screenshots can remain a manual QA
     attachment unless CI has a stable desktop session.

3. Make the reader panel width screen-aware.
   - Clamp width to the current monitor, for example
     `min(760, screen_width - safe_margin)`.
   - Re-measure header labels, close button hit area, and karaoke wrapping
     on narrow displays.

4. Repeat live E2E after closing the installed app on port 51677.
   - Command: `.\e2e\run-local.ps1 -SkipSetup`
   - Expected blocker-free proof: all public live UI tests pass against the
     isolated `.e2e\data\public` data root.

## Validation

- `python -m pytest tests\test_settings_window.py tests\test_tray.py tests\test_theme.py -q`
  - Result: `7 passed in 0.23s`
- `python -m ruff check src\pippal\ui\settings_window.py src\pippal\ui\settings_cards.py tests\test_settings_window.py tests\test_tray.py tests\test_theme.py`
  - Result: `All checks passed!`
- `.\e2e\run-local.ps1 -SkipSetup`
  - Result: blocked before app launch by `127.0.0.1:51677 is already in use. Close running PipPal instances first.`
  - Owner: PID 12620, installed `PipPal.exe` from `BugFactory.pippal-pro_0.2.2.0_x64__km6tvv8cv49he`.

## Teaching Note

This uses a measured responsive-polish pattern: first collect widget
request widths at target scaling, then fix only controls with proven
clipping. The chosen approach keeps changes local to Tk layout instead
of rewriting the Settings design. Alternatives were increasing the
minimum window width or shortening labels. The tradeoff is a slightly
taller footer at high DPI, but the window remains small-screen friendly
and all critical action buttons stay readable.
