"""Maintained editor / terminal / chat selected-text UI smokes (issue #61).

Sibling of ``test_selected_text_smokes.py`` (issue #62) and
``test_pdf_smokes.py`` (issue #63) for the v0.2.5 release. This module
extends the same harness contract to the daily-use surfaces named by
the selected-text reliability matrix:

- Editor: VS Code with a known plain-text fixture. Notepad++ is a
  documented fallback when VS Code is not on the gate machine.
- Terminal: Windows Terminal with a known buffer line, plus a legacy
  ``powershell.exe`` console row whose copy semantics require a mouse
  selection and are therefore not unattended-smokable. The terminal
  surface's required copy setting is documented in the smoke docstring
  and in ``docs/SELECTED_TEXT_RELIABILITY.md``.
- Chat / email body: Teams, Outlook, and Discord absences or sign-in
  blockers are recorded as ``unavailable`` / ``blocked`` per the
  release-gate status contract, not as silent pytest skips.

Track: daily-use, not Gate 3. Failures on these smokes do not block
release on their own; the release-gate must-pass list in
``docs/RELEASE_CHECKLIST.md`` Gate 3 remains the #62/#63 surfaces.
Issue #61 broadens the reliability matrix without broadening
compatibility wording.

Each smoke either verifies exact capture + clipboard restoration
(matching the #62/#63 contract) or records a structured
``failure_symptom`` / ``candidate_fix`` evidence file when the surface
is reachable but the gate machine cannot drive it unattended.
"""

from __future__ import annotations

import subprocess
import time
from pathlib import Path

import pytest

from . import _harness as harness

pytestmark = pytest.mark.ui_smoke


# ---------------------------------------------------------------------------
# Fixture text and sentinels.
# ---------------------------------------------------------------------------


VSCODE_TEXT = (
    "PipPal issue 61 VS Code selected-text smoke: capture_selection "
    "must copy this exact editor sentence and restore the previous clipboard."
)
VSCODE_SENTINEL = "ISSUE61_VSCODE_PREVIOUS_CLIPBOARD"

NOTEPAD_PP_SENTINEL = "ISSUE61_NOTEPADPP_PREVIOUS_CLIPBOARD"

# The terminal buffer line is short and ASCII so the WT selection
# model includes it verbatim — multi-line and wrapped selections in
# the terminal carry trailing whitespace that varies by column width
# and wrap mode, neither of which is part of this smoke's contract.
TERMINAL_BUFFER_LINE = (
    "PipPal issue 61 terminal selected-text smoke sentence."
)
TERMINAL_SENTINEL = "ISSUE61_TERMINAL_PREVIOUS_CLIPBOARD"
TERMINAL_TAB_TITLE = "pippal-issue61-terminal-smoke"

POWERSHELL_LEGACY_SENTINEL = "ISSUE61_POWERSHELL_LEGACY_PREVIOUS_CLIPBOARD"

TEAMS_SENTINEL = "ISSUE61_TEAMS_PREVIOUS_CLIPBOARD"
OUTLOOK_SENTINEL = "ISSUE61_OUTLOOK_PREVIOUS_CLIPBOARD"
DISCORD_SENTINEL = "ISSUE61_DISCORD_PREVIOUS_CLIPBOARD"


def _write_unavailable_evidence(
    *,
    evidence_dir: Path,
    smoke_id: str,
    surface: str,
    sentinel: str,
    expected_text: str,
    searched: list[str],
    rationale: str,
) -> Path:
    """Write a structured ``unavailable`` evidence file and return its path.

    Centralised because issue #61 has many absent-surface rows; keeping
    one writer prevents drift between the chat/editor/terminal not-
    installed paths.
    """

    evidence = harness.SmokeEvidence(
        smoke_id=smoke_id,
        surface=surface,
        app_path="",
        app_version="not installed",
        fixture_path="",
        expected_text=expected_text,
        captured_text="",
        matched_expected=False,
        previous_clipboard_sentinel=sentinel,
        clipboard_after_capture="",
        clipboard_restored=False,
        duration_s=0.0,
        extra={
            "status": "unavailable",
            "searched_paths": searched,
            "rationale": rationale,
        },
    )
    return evidence.write(evidence_dir)


def _write_blocked_evidence(
    *,
    evidence_dir: Path,
    smoke_id: str,
    surface: str,
    sentinel: str,
    expected_text: str,
    app_path: str,
    app_version: str,
    failure_symptom: str,
    candidate_fix: str,
    extra: dict[str, str] | None = None,
) -> Path:
    """Write a structured ``blocked`` evidence file and return its path.

    Used when the surface is present on the gate machine but cannot be
    driven unattended (Teams sign-in, Outlook profile picker, legacy
    console mark-mode mouse selection). Matches the issue #63 Acrobat
    pattern: machine-readable evidence the release reviewer can act on
    rather than a silent skip.
    """

    payload = {
        "status": "blocked",
        "failure_symptom": failure_symptom,
        "candidate_fix": candidate_fix,
    }
    if extra:
        payload.update(extra)
    evidence = harness.SmokeEvidence(
        smoke_id=smoke_id,
        surface=surface,
        app_path=app_path,
        app_version=app_version,
        fixture_path="",
        expected_text=expected_text,
        captured_text="",
        matched_expected=False,
        previous_clipboard_sentinel=sentinel,
        clipboard_after_capture="",
        clipboard_restored=False,
        duration_s=0.0,
        extra=payload,
    )
    return evidence.write(evidence_dir)


# ---------------------------------------------------------------------------
# Editor smokes — VS Code happy path + Notepad++ fallback row.
# ---------------------------------------------------------------------------


def test_vscode_selected_text_or_unavailable(
    vscode_exe: Path | None,
    evidence_dir: Path,
    tmp_path_factory: pytest.TempPathFactory,
) -> None:
    """VS Code happy path when installed, structured ``unavailable`` otherwise.

    VS Code is an Electron app: its Chromium renderer accepts
    ``Ctrl+A`` and ``Ctrl+C`` from HID-level injection
    (``send_hotkey_via_keyboard_lib``) the same way Edge's PDF.js
    iframe does. ``System.Windows.Forms.SendKeys.SendWait`` is not used
    here because the Electron renderer ignores synthetic SendKeys
    events directed at the document area on first focus, mirroring the
    Edge PDF behaviour established in #63.

    The smoke uses a throwaway ``--user-data-dir`` and
    ``--extensions-dir`` so the user's real VS Code profile is never
    touched (no recent-files list, no signed-in account, no
    extensions). ``--disable-extensions`` is belt-and-braces against a
    user-installed extension that grabs ``Ctrl+A``.
    """

    if vscode_exe is None:
        searched = [str(p) for p in harness.VSCODE_CANDIDATES]
        _write_unavailable_evidence(
            evidence_dir=evidence_dir,
            smoke_id="vscode_selected_text_unavailable",
            surface="VS Code (not installed)",
            sentinel=VSCODE_SENTINEL,
            expected_text=VSCODE_TEXT,
            searched=searched,
            rationale=(
                "Code.exe not found in PATH or any of the known install "
                "locations on this gate machine. Recorded as unavailable "
                "per the release-gate status contract."
            ),
        )
        pytest.skip(
            f"VS Code not installed (searched {searched}); "
            "evidence recorded as unavailable"
        )

    fixture_dir = tmp_path_factory.mktemp("pippal_issue61_vscode")
    user_data_dir = fixture_dir / "vscode-user-data"
    extensions_dir = fixture_dir / "vscode-extensions"
    fixture_path = fixture_dir / "pippal_issue61_vscode.txt"
    fixture_path.write_text(VSCODE_TEXT, encoding="utf-8")

    app_version = harness.get_file_product_version(vscode_exe)
    process = harness.launch_vscode(
        vscode_exe,
        fixture_path,
        user_data_dir=user_data_dir,
        extensions_dir=extensions_dir,
    )
    started = time.monotonic()
    try:
        title_ready = harness.wait_for_vscode_title(fixture_path)
        assert title_ready, (
            f"VS Code window for {fixture_path.name} did not appear in "
            "the OS window list within the load timeout; the editor "
            "may have stalled on a first-run prompt"
        )

        # Cold-start focus race recovery loop, same shape as the Edge
        # webpage smoke: try up to 5 times to land focus on the editor
        # area and capture the selection. Electron's renderer can take
        # a couple of paint frames before the file content is keyboard-
        # reachable; the fixture content does not change between
        # attempts.
        captured = ""
        clipboard_after = ""
        focused = False
        for attempt in range(5):
            focused = harness.activate_window_by_exact_title_substring(
                harness.vscode_window_title(fixture_path),
                process_names=("Code",),
                attempts=30,
            )
            if not focused:
                continue
            if attempt > 0:
                # Nudge focus into the editor pane on retry. Clicking
                # the window centre is the same primitive the PDF
                # smokes use for the PDF.js iframe; the editor area is
                # in the centre of a freshly-opened VS Code window.
                harness.click_into_window_center(
                    harness.vscode_window_title(fixture_path)
                )
                time.sleep(0.3)
            # Settle so VS Code finishes wiring up the editor model
            # before Ctrl+A reaches it.
            time.sleep(0.6)
            if not harness.send_hotkey_via_keyboard_lib("ctrl+a"):
                continue
            time.sleep(0.3)
            captured, clipboard_after = harness.capture_with_sentinel_clipboard(
                sentinel=VSCODE_SENTINEL,
            )
            if captured == VSCODE_TEXT:
                break

        evidence = harness.SmokeEvidence(
            smoke_id="vscode_selected_text_happy_path",
            surface="VS Code editor (plain text)",
            app_path=str(vscode_exe),
            app_version=app_version,
            fixture_path=str(fixture_path),
            expected_text=VSCODE_TEXT,
            captured_text=captured,
            matched_expected=(captured == VSCODE_TEXT),
            previous_clipboard_sentinel=VSCODE_SENTINEL,
            clipboard_after_capture=clipboard_after,
            clipboard_restored=(clipboard_after == VSCODE_SENTINEL),
            duration_s=time.monotonic() - started,
            extra={
                "selection_method": "keyboard.send('ctrl+a') HID-level injection",
                "focus_method": (
                    "activate_window_by_exact_title_substring + "
                    "click_into_window_center retry"
                ),
                "user_data_dir": str(user_data_dir),
                "extensions_dir": str(extensions_dir),
                "vscode_flags": (
                    "-n --disable-extensions --user-data-dir --extensions-dir "
                    "--skip-release-notes --skip-welcome"
                ),
            },
        )
        evidence.write(evidence_dir)

        assert focused, (
            f"VS Code window for {fixture_path.name} did not accept "
            "focus; a first-run prompt may have stolen the foreground"
        )
        assert captured == VSCODE_TEXT, (
            f"VS Code capture mismatch.\n"
            f"  expected: {VSCODE_TEXT!r}\n"
            f"  captured: {captured!r}\n"
            f"  app: {vscode_exe} ({app_version})"
        )
        assert clipboard_after == VSCODE_SENTINEL, (
            "VS Code smoke left the clipboard unrestored. "
            f"expected sentinel {VSCODE_SENTINEL!r}, "
            f"clipboard now {clipboard_after!r}."
        )
    finally:
        try:
            process.terminate()
        except Exception:
            pass
        harness.force_close_vscode_for(user_data_dir)


def test_notepad_pp_selected_text_or_unavailable(
    notepad_pp_exe: Path | None,
    evidence_dir: Path,
    tmp_path_factory: pytest.TempPathFactory,
) -> None:
    """Notepad++ happy path when installed, structured ``unavailable`` otherwise.

    Notepad++ is the documented fallback editor for the reliability
    matrix: a non-Electron Win32 editor whose ``Ctrl+A`` /  ``Ctrl+C``
    surface is reachable via ``SendKeys`` (no HID-level injection
    needed). The smoke is identical in shape to the Notepad happy
    path in #62 — only the executable and fixture content differ.
    """

    if notepad_pp_exe is None:
        searched = [str(p) for p in harness.NOTEPAD_PP_CANDIDATES]
        _write_unavailable_evidence(
            evidence_dir=evidence_dir,
            smoke_id="notepad_pp_selected_text_unavailable",
            surface="Notepad++ (not installed)",
            sentinel=NOTEPAD_PP_SENTINEL,
            expected_text=VSCODE_TEXT,
            searched=searched,
            rationale=(
                "notepad++.exe not found in PATH or any of the known "
                "install locations on this gate machine. Recorded as "
                "unavailable per the release-gate status contract; "
                "Notepad++ is the documented fallback when VS Code is "
                "absent, so a green VS Code smoke covers the editor "
                "surface for the matrix."
            ),
        )
        pytest.skip(
            f"Notepad++ not installed (searched {searched}); "
            "evidence recorded as unavailable"
        )

    fixture_dir = tmp_path_factory.mktemp("pippal_issue61_npp")
    fixture_path = fixture_dir / "pippal_issue61_npp.txt"
    fixture_path.write_text(VSCODE_TEXT, encoding="utf-8")

    app_version = harness.get_file_product_version(notepad_pp_exe)
    process = subprocess.Popen(
        [str(notepad_pp_exe), "-multiInst", "-nosession", str(fixture_path)]
    )
    started = time.monotonic()
    try:
        focused = harness.activate_window_by_exact_title_substring(
            fixture_path.name,
            process_names=("notepad++",),
            attempts=30,
        )
        assert focused, (
            f"Notepad++ window for {fixture_path.name} did not accept "
            "focus; another modal window may be in the foreground"
        )

        selected = harness.send_keys_to_foreground("^a")
        assert selected, "SendKeys ^a (select-all) into Notepad++ failed"
        time.sleep(0.2)

        captured, clipboard_after = harness.capture_with_sentinel_clipboard(
            sentinel=NOTEPAD_PP_SENTINEL,
        )

        evidence = harness.SmokeEvidence(
            smoke_id="notepad_pp_selected_text_happy_path",
            surface="Notepad++ editor (plain text)",
            app_path=str(notepad_pp_exe),
            app_version=app_version,
            fixture_path=str(fixture_path),
            expected_text=VSCODE_TEXT,
            captured_text=captured,
            matched_expected=(captured == VSCODE_TEXT),
            previous_clipboard_sentinel=NOTEPAD_PP_SENTINEL,
            clipboard_after_capture=clipboard_after,
            clipboard_restored=(clipboard_after == NOTEPAD_PP_SENTINEL),
            duration_s=time.monotonic() - started,
            extra={
                "selection_method": "SendKeys ^a",
                "focus_method": "activate_window_by_exact_title_substring",
                "launch_flags": "-multiInst -nosession",
            },
        )
        evidence.write(evidence_dir)

        assert captured == VSCODE_TEXT, (
            f"Notepad++ capture mismatch.\n"
            f"  expected: {VSCODE_TEXT!r}\n"
            f"  captured: {captured!r}\n"
            f"  app: {notepad_pp_exe} ({app_version})"
        )
        assert clipboard_after == NOTEPAD_PP_SENTINEL, (
            "Notepad++ smoke left the clipboard unrestored. "
            f"expected sentinel {NOTEPAD_PP_SENTINEL!r}, "
            f"clipboard now {clipboard_after!r}."
        )
    finally:
        try:
            process.terminate()
        except Exception:
            pass
        script = (
            "Get-Process -Name notepad++ -ErrorAction SilentlyContinue | "
            "Where-Object { $_.MainWindowTitle -like "
            f"'*{fixture_path.name}*'"
            " } | Stop-Process -Force -ErrorAction SilentlyContinue"
        )
        harness.run_powershell(script, timeout=10.0)


# ---------------------------------------------------------------------------
# Terminal smokes — Windows Terminal + legacy powershell.exe console.
# ---------------------------------------------------------------------------


def test_windows_terminal_buffer_selected_text_or_blocked(
    windows_terminal_exe: Path | None,
    evidence_dir: Path,
) -> None:
    """Windows Terminal buffer selection happy path or structured outcome.

    Required Windows Terminal copy settings on this gate machine:

    - ``selectAll`` action default keybinding ``ctrl+shift+a`` (selects
      the entire buffer, including the scrollback we just wrote).
    - ``copy`` action default keybinding ``ctrl+shift+c`` (writes the
      current selection to the clipboard).
    - ``copyOnSelect`` defaults to ``false``. When ``copyOnSelect`` is
      ``false`` *and* a selection is active, the ``copy`` action also
      runs on ``ctrl+c`` per the Windows Terminal default keybindings
      shipped from v1.16 onwards — this is the surface PipPal's
      capture helper (``Ctrl+C`` injection) actually exercises.

    The smoke:

    1. Opens a Windows Terminal tab whose title is uniquely matchable.
    2. Runs an inline ``pwsh`` command that emits the fixture sentence
       on its own line. ``-NoExit`` keeps the buffer alive.
    3. Sends ``ctrl+shift+a`` via HID-level injection (the same path
       PDF smokes use) — ``System.Windows.Forms.SendKeys.SendWait`` is
       not reliable for the Windows Terminal control surface.
    4. Calls ``capture_selection``, which sends ``Ctrl+C`` to the
       terminal. On a default-configured WT this either copies the
       selection (happy path) or fires SIGINT in the shell (blocked
       surface with a documented ``candidate_fix``: enable
       ``copyOnSelect`` or rebind ``copy`` to ``ctrl+c``).

    The smoke asserts that *whatever* happens, the clipboard sentinel
    is preserved on the non-capture path. PipPal must never destroy
    the user's clipboard when the terminal's copy semantics produce
    no captured text.
    """

    if windows_terminal_exe is None:
        searched = [
            r"C:\Users\<user>\AppData\Local\Microsoft\WindowsApps\wt.exe",
            "PATH lookup of wt.exe",
        ]
        _write_unavailable_evidence(
            evidence_dir=evidence_dir,
            smoke_id="windows_terminal_buffer_unavailable",
            surface="Windows Terminal (not installed)",
            sentinel=TERMINAL_SENTINEL,
            expected_text=TERMINAL_BUFFER_LINE,
            searched=searched,
            rationale=(
                "wt.exe not found via PATH or the WindowsApps Store shim "
                "directory on this gate machine. Windows Terminal is "
                "Appx-distributed; an absent shim means the package is "
                "not installed for the current user. Recorded as "
                "unavailable per the release-gate status contract."
            ),
        )
        pytest.skip(
            f"Windows Terminal not installed (searched {searched}); "
            "evidence recorded as unavailable"
        )

    app_version = harness.get_file_product_version(windows_terminal_exe)

    # Inline command: write the fixture sentence to the buffer, then
    # park the shell so the buffer stays selectable. We use
    # ``Write-Host`` (not ``echo``/``Write-Output``) because Write-Host
    # always emits to the console buffer regardless of the
    # ``$OutputEncoding`` / pipeline state.
    inline = (
        f"Write-Host '{TERMINAL_BUFFER_LINE}'; "
        # Tiny settle so the line is fully flushed to the buffer
        # before the smoke pumps the keyboard.
        "Start-Sleep -Milliseconds 200"
    )

    process = harness.launch_windows_terminal(
        windows_terminal_exe,
        title=TERMINAL_TAB_TITLE,
        inline_command=inline,
    )
    started = time.monotonic()
    captured = ""
    clipboard_after = ""
    focused = False
    try:
        title_ready = harness.wait_for_windows_terminal_title(TERMINAL_TAB_TITLE)
        if not title_ready:
            _write_blocked_evidence(
                evidence_dir=evidence_dir,
                smoke_id="windows_terminal_buffer_blocked_no_window_title",
                surface="Windows Terminal (host slow to publish title)",
                sentinel=TERMINAL_SENTINEL,
                expected_text=TERMINAL_BUFFER_LINE,
                app_path=str(windows_terminal_exe),
                app_version=app_version,
                failure_symptom=(
                    f"Windows Terminal window titled {TERMINAL_TAB_TITLE!r} "
                    "did not appear in the OS window list within the load "
                    "timeout. The Appx-hosted WindowsTerminal.exe may have "
                    "started a fresh process tree and not yet finished "
                    "rendering the requested tab title."
                ),
                candidate_fix=(
                    "Pre-warm Windows Terminal once on the gate machine "
                    "(launch and close wt.exe) so the subsequent smoke run "
                    "uses an already-cached Appx host. Alternatively, raise "
                    "wait_for_windows_terminal_title timeout above 30s."
                ),
            )
            pytest.skip(
                "Windows Terminal host did not publish requested title in "
                "time; recorded as blocked"
            )

        focused = harness.activate_window_by_exact_title_substring(
            TERMINAL_TAB_TITLE,
            process_names=("WindowsTerminal",),
            attempts=30,
        )
        if not focused:
            _write_blocked_evidence(
                evidence_dir=evidence_dir,
                smoke_id="windows_terminal_buffer_blocked_no_focus",
                surface="Windows Terminal (focus refused)",
                sentinel=TERMINAL_SENTINEL,
                expected_text=TERMINAL_BUFFER_LINE,
                app_path=str(windows_terminal_exe),
                app_version=app_version,
                failure_symptom=(
                    "WindowsTerminal.exe published the requested tab title "
                    "but SetForegroundWindow could not move focus to its "
                    "main window within the configured attempts. A "
                    "non-modal pane on the gate machine may be holding "
                    "the foreground."
                ),
                candidate_fix=(
                    "Close any pinned Windows Terminal window on the gate "
                    "machine before re-running the smoke. If the focus "
                    "block persists, file a follow-up issue per the "
                    "daily-use track in SELECTED_TEXT_RELIABILITY.md."
                ),
            )
            pytest.skip("Windows Terminal refused focus; recorded as blocked")

        # Settle while the shell finishes printing the buffer line.
        time.sleep(0.6)
        # Drive the documented Windows Terminal select-all binding.
        assert harness.send_hotkey_via_keyboard_lib("ctrl+shift+a"), (
            "HID-level ctrl+shift+a injection failed; the keyboard "
            "library could not reach the Windows Terminal host"
        )
        time.sleep(0.4)

        captured, clipboard_after = harness.capture_with_sentinel_clipboard(
            sentinel=TERMINAL_SENTINEL,
        )
        # WT joins the selected buffer with platform line endings and
        # pads the right edge with spaces to the column width. We
        # accept a match where the fixture sentence appears on one of
        # the captured lines after right-stripping.
        captured_lines = [
            line.rstrip()
            for line in captured.replace("\r\n", "\n").split("\n")
            if line.strip()
        ]
        matched = TERMINAL_BUFFER_LINE in captured_lines

        if matched:
            evidence = harness.SmokeEvidence(
                smoke_id="windows_terminal_buffer_selected_text_happy_path",
                surface="Windows Terminal buffer (Ctrl+Shift+A select-all)",
                app_path=str(windows_terminal_exe),
                app_version=app_version,
                fixture_path="",
                expected_text=TERMINAL_BUFFER_LINE,
                captured_text=captured,
                matched_expected=True,
                previous_clipboard_sentinel=TERMINAL_SENTINEL,
                clipboard_after_capture=clipboard_after,
                clipboard_restored=(clipboard_after == TERMINAL_SENTINEL),
                duration_s=time.monotonic() - started,
                extra={
                    "selection_method": (
                        "keyboard.send('ctrl+shift+a') -> WT default selectAll"
                    ),
                    "copy_method": (
                        "capture_selection drives Ctrl+C; WT default "
                        "keybindings (v1.16+) bind copy to ctrl+c when a "
                        "selection is active"
                    ),
                    "focus_method": (
                        "activate_window_by_exact_title_substring with "
                        "WindowsTerminal process filter"
                    ),
                    "wt_terminal_version": str(app_version),
                    "required_settings": (
                        "selectAll bound to ctrl+shift+a (default); "
                        "copy bound to ctrl+shift+c (default); "
                        "copy also fires on ctrl+c when a selection is "
                        "active (default in WT >= 1.16)"
                    ),
                },
            )
            evidence.write(evidence_dir)

            assert clipboard_after == TERMINAL_SENTINEL, (
                "Windows Terminal smoke left the clipboard unrestored. "
                f"expected sentinel {TERMINAL_SENTINEL!r}, "
                f"clipboard now {clipboard_after!r}."
            )
        else:
            _write_blocked_evidence(
                evidence_dir=evidence_dir,
                smoke_id="windows_terminal_buffer_blocked_copy_semantics",
                surface=(
                    "Windows Terminal buffer (Ctrl+C did not copy the "
                    "selection)"
                ),
                sentinel=TERMINAL_SENTINEL,
                expected_text=TERMINAL_BUFFER_LINE,
                app_path=str(windows_terminal_exe),
                app_version=app_version,
                failure_symptom=(
                    "Ctrl+Shift+A selected the buffer and the WT tab held "
                    "the foreground, but the Ctrl+C that capture_selection "
                    "drives did not write the selection to the clipboard. "
                    "Either the gate machine's settings.json overrides the "
                    "default copy keybinding, or Ctrl+C reached the running "
                    "shell as SIGINT and cancelled the selection."
                ),
                candidate_fix=(
                    "Enable `copyOnSelect: true` in the Windows Terminal "
                    "settings.json, or rebind the `copy` action to "
                    "`ctrl+c` explicitly. PipPal Core should detect the "
                    "WindowsTerminal.exe foreground process and fall back "
                    "to `ctrl+shift+c` in a future capture-path enhancement."
                ),
                extra={
                    "captured_text_repr": repr(captured),
                    "clipboard_after_capture": clipboard_after,
                    "clipboard_restored": str(
                        clipboard_after == TERMINAL_SENTINEL
                    ),
                },
            )
            assert clipboard_after == TERMINAL_SENTINEL, (
                "Windows Terminal blocked-copy smoke clobbered the "
                f"clipboard. expected sentinel {TERMINAL_SENTINEL!r}, "
                f"clipboard now {clipboard_after!r}. "
                "Core must restore the previous clipboard even when the "
                "terminal's copy semantics produce no captured text."
            )
            pytest.skip(
                "Windows Terminal Ctrl+C did not copy the selection on "
                "this gate machine; recorded as blocked with a "
                "documented candidate_fix"
            )
    finally:
        try:
            process.terminate()
        except Exception:
            pass
        harness.force_close_windows_terminal_for(TERMINAL_TAB_TITLE)


def test_powershell_legacy_console_blocked(
    powershell_legacy_exe: Path | None,
    evidence_dir: Path,
) -> None:
    """Legacy ``powershell.exe`` console (conhost) is not unattended-smokable.

    Windows PowerShell 5.1's conhost-hosted console does not expose a
    keyboard select-all action. The documented copy workflow is:

    1. Press ``Alt+Space``, ``E``, ``K`` to enter Mark mode (or rely on
       ``QuickEdit Mode`` being enabled and use mouse drag).
    2. Use arrow keys or the mouse to highlight a buffer region.
    3. Press ``Enter`` to copy the highlighted region to the clipboard.

    None of those steps are reachable from synthetic ``Ctrl+A`` /
    ``Ctrl+C`` injection — Mark mode arrow-key selection cannot be
    primed without sending Alt-Space-E-K as a deterministic keystroke
    sequence the legacy console will accept, and the menu hot-key
    surface is locale-dependent (the ``E`` and ``K`` letters change on
    a localised Windows install).

    Per the release-gate status contract, this smoke records
    ``blocked`` with a structured ``failure_symptom`` and
    ``candidate_fix`` rather than attempting a fragile menu-driven
    automation. The candidate fix is to direct users at Windows
    Terminal (the modern default) when capture from a legacy console
    is required.
    """

    if powershell_legacy_exe is None:
        _write_unavailable_evidence(
            evidence_dir=evidence_dir,
            smoke_id="powershell_legacy_console_unavailable",
            surface="Windows PowerShell 5.1 console (not installed)",
            sentinel=POWERSHELL_LEGACY_SENTINEL,
            expected_text="",
            searched=[r"C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe"],
            rationale=(
                "Windows PowerShell 5.1 ships on every supported Windows "
                "install, so a missing executable is itself anomalous. "
                "Recorded for completeness."
            ),
        )
        pytest.skip(
            "Windows PowerShell 5.1 not found on this gate machine; "
            "evidence recorded as unavailable"
        )

    app_version = harness.get_file_product_version(powershell_legacy_exe)
    _write_blocked_evidence(
        evidence_dir=evidence_dir,
        smoke_id="powershell_legacy_console_blocked",
        surface="Windows PowerShell 5.1 console (conhost mark mode)",
        sentinel=POWERSHELL_LEGACY_SENTINEL,
        expected_text="",
        app_path=str(powershell_legacy_exe),
        app_version=app_version,
        failure_symptom=(
            "The legacy conhost-hosted Windows PowerShell console does "
            "not expose a keyboard select-all binding. Buffer copy "
            "requires either Mark mode (Alt+Space -> E -> K, then "
            "arrow-key highlight, then Enter) or QuickEdit mouse drag, "
            "neither of which is reachable from the synthetic Ctrl+A / "
            "Ctrl+C injection PipPal Core drives."
        ),
        candidate_fix=(
            "Document Windows Terminal as the supported terminal "
            "surface in user-facing release notes. Users on the legacy "
            "console can either migrate to Windows Terminal (default on "
            "Win11) or mouse-select a buffer region before pressing the "
            "PipPal read-selection hotkey, which falls back to the "
            "currently-highlighted region via the QuickEdit copy-on-"
            "enter path."
        ),
        extra={
            "release_notes_constraint": (
                "Marketing wording must say 'Windows Terminal' explicitly "
                "when terminal-buffer capture is claimed, not generic "
                "'Windows terminal' which would imply legacy conhost."
            ),
        },
    )
    pytest.skip(
        "Legacy powershell.exe console mark-mode capture is not "
        "unattended-smokable; recorded as blocked with documented "
        "candidate_fix"
    )


# ---------------------------------------------------------------------------
# Chat / email body smokes — Teams / Outlook / Discord.
# ---------------------------------------------------------------------------


def test_teams_chat_body_blocked_or_unavailable(
    teams_exe: Path | None,
    evidence_dir: Path,
) -> None:
    """Teams chat-body capture cannot run on an unattended gate machine.

    Teams (Store / new client) launches into a sign-in flow on first
    launch and a tenant-selection / cached-credential refresh on every
    cold start when no live session is cached. Neither flow is
    reachable from synthetic keyboard injection without a configured
    corporate account; the chat-body surface is consequently hidden
    behind a modal the smoke cannot dismiss.

    Per the release-gate status contract, we record:

    - ``unavailable`` when no Teams install is found (no follow-up
      action required for that case).
    - ``blocked`` with a structured ``candidate_fix`` when Teams is
      installed but cannot be driven unattended. The release engineer
      provides manual evidence before any Teams-specific claim lands
      in release notes.
    """

    if teams_exe is None:
        searched = [str(p) for p in harness.TEAMS_CANDIDATES]
        _write_unavailable_evidence(
            evidence_dir=evidence_dir,
            smoke_id="teams_chat_body_unavailable",
            surface="Microsoft Teams (not installed)",
            sentinel=TEAMS_SENTINEL,
            expected_text="",
            searched=searched,
            rationale=(
                "ms-teams.exe Appx shim not found in the WindowsApps "
                "directory or PATH. Recorded as unavailable per the "
                "release-gate status contract."
            ),
        )
        pytest.skip(
            f"Teams not installed (searched {searched}); "
            "evidence recorded as unavailable"
        )

    app_version = harness.get_file_product_version(teams_exe)
    _write_blocked_evidence(
        evidence_dir=evidence_dir,
        smoke_id="teams_chat_body_blocked_requires_signin",
        surface="Microsoft Teams chat body (requires interactive sign-in)",
        sentinel=TEAMS_SENTINEL,
        expected_text="",
        app_path=str(teams_exe),
        app_version=app_version,
        failure_symptom=(
            "Teams cold-launches into a tenant-selection / sign-in flow "
            "before any chat body is reachable. The flow is not "
            "scriptable from synthetic keyboard injection without an "
            "active corporate account on the gate machine, so the "
            "chat-body selected-text surface cannot be smoked unattended."
        ),
        candidate_fix=(
            "Until Teams claims appear in release notes, the release "
            "engineer supplies manual evidence: select a chat-message "
            "paragraph in Teams, press the PipPal read-selection "
            "hotkey, and attach the captured-text screenshot to the "
            "release PR. Teams chat-body capture must not be promoted "
            "to release notes without that evidence."
        ),
        extra={
            "release_notes_constraint": (
                "Marketing wording must not claim 'works in Teams' "
                "until manual evidence is attached to the release PR."
            ),
        },
    )
    pytest.skip(
        "Teams chat-body capture requires interactive sign-in on this "
        "gate machine; recorded as blocked with documented candidate_fix"
    )


def test_outlook_message_body_blocked_or_unavailable(
    outlook_exe: Path | None,
    evidence_dir: Path,
) -> None:
    """Outlook message-body capture cannot run on an unattended gate machine.

    A cold-start ``OUTLOOK.EXE`` opens a profile picker (or a forced
    OST sync) before any composable message body is on screen. Without
    a configured mail profile, the composer surface is unreachable.
    The smoke records this as ``blocked`` with a structured
    ``candidate_fix`` rather than attempting a fragile profile-picker
    automation that would race against the version-specific Outlook
    UI shell.
    """

    if outlook_exe is None:
        searched = [str(p) for p in harness.OUTLOOK_CANDIDATES]
        _write_unavailable_evidence(
            evidence_dir=evidence_dir,
            smoke_id="outlook_message_body_unavailable",
            surface="Outlook (not installed)",
            sentinel=OUTLOOK_SENTINEL,
            expected_text="",
            searched=searched,
            rationale=(
                "OUTLOOK.EXE not found in PATH or any of the known "
                "Microsoft Office install locations on this gate "
                "machine. Recorded as unavailable per the release-gate "
                "status contract."
            ),
        )
        pytest.skip(
            f"Outlook not installed (searched {searched}); "
            "evidence recorded as unavailable"
        )

    app_version = harness.get_file_product_version(outlook_exe)
    _write_blocked_evidence(
        evidence_dir=evidence_dir,
        smoke_id="outlook_message_body_blocked_requires_profile",
        surface="Outlook message body (requires configured mail profile)",
        sentinel=OUTLOOK_SENTINEL,
        expected_text="",
        app_path=str(outlook_exe),
        app_version=app_version,
        failure_symptom=(
            "Outlook cold-launches into a profile picker or OST sync "
            "before a composer window with a selectable message body "
            "is on screen. Driving the profile picker from synthetic "
            "keyboard injection is fragile because the dialog layout "
            "depends on the installed Outlook channel and patch level."
        ),
        candidate_fix=(
            "Until Outlook claims appear in release notes, the release "
            "engineer supplies manual evidence: select a body paragraph "
            "in a draft message, press the PipPal read-selection "
            "hotkey, and attach the captured-text screenshot to the "
            "release PR. Outlook message-body capture must not be "
            "promoted to release notes without that evidence."
        ),
        extra={
            "release_notes_constraint": (
                "Marketing wording must not claim 'works in Outlook' "
                "until manual evidence is attached to the release PR."
            ),
        },
    )
    pytest.skip(
        "Outlook message-body capture requires a configured mail "
        "profile on this gate machine; recorded as blocked with "
        "documented candidate_fix"
    )


def test_discord_message_body_unavailable(
    discord_exe: Path | None,
    evidence_dir: Path,
) -> None:
    """Discord chat-body capture row, ``unavailable`` when no install is found.

    Discord is the third documented communication surface from the
    reliability matrix. It is not installed on this gate machine; the
    smoke records the absence as ``unavailable`` with the searched
    paths so the release reviewer can verify the surface coverage
    without having to inspect the test source.
    """

    if discord_exe is None:
        searched = [
            r"C:\Users\<user>\AppData\Local\Discord\app-*\Discord.exe",
        ]
        _write_unavailable_evidence(
            evidence_dir=evidence_dir,
            smoke_id="discord_message_body_unavailable",
            surface="Discord (not installed)",
            sentinel=DISCORD_SENTINEL,
            expected_text="",
            searched=searched,
            rationale=(
                "Discord per-user install directory not found. "
                "Recorded as unavailable per the release-gate status "
                "contract."
            ),
        )
        pytest.skip(
            f"Discord not installed (searched {searched}); "
            "evidence recorded as unavailable"
        )

    # Discord installed: same sign-in blocker as Teams. We record
    # ``blocked`` rather than attempting an automation; the structure
    # matches the Teams / Outlook smokes so the reliability matrix
    # rows stay consistent.
    app_version = harness.get_file_product_version(discord_exe)
    _write_blocked_evidence(
        evidence_dir=evidence_dir,
        smoke_id="discord_message_body_blocked_requires_signin",
        surface="Discord message body (requires interactive sign-in)",
        sentinel=DISCORD_SENTINEL,
        expected_text="",
        app_path=str(discord_exe),
        app_version=app_version,
        failure_symptom=(
            "Discord cold-launches into a sign-in / 2FA flow before "
            "any chat-message body is reachable. The flow is not "
            "scriptable from synthetic keyboard injection without an "
            "active session, so the chat-body selected-text surface "
            "cannot be smoked unattended."
        ),
        candidate_fix=(
            "Until Discord claims appear in release notes, the "
            "release engineer supplies manual evidence: select a "
            "message-body paragraph in Discord, press the PipPal "
            "read-selection hotkey, and attach the captured-text "
            "screenshot to the release PR."
        ),
    )
    pytest.skip(
        "Discord message-body capture requires interactive sign-in on "
        "this gate machine; recorded as blocked with documented "
        "candidate_fix"
    )
