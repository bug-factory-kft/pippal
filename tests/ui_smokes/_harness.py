"""Foreign-app driver helpers for the maintained selected-text UI smokes.

This module is the *small* extension of the existing live UI evidence
gate (`e2e/`) — it does not replace it. The live UI gate proves the
PipPal desktop app's own widgets; these smokes prove the source
``pippal.clipboard_capture.capture_selection`` helper against a foreign
app (Notepad / Edge / VS Code / PDF viewers) that the user actually
selects text in.

Two design rules:

1. **Selection must be set up by an external proven path**, not by the
   capture helper itself. ``WScript.Shell.AppActivate`` is no longer
   the proven path: it does fuzzy title matching (on a gate machine
   with 15+ Serena Dashboard windows it latches onto the wrong window
   and silently drives Ctrl+A there, corrupting the user's clipboard),
   and on modern Win11 Notepad ``SendKeys ^a`` reaches the title bar
   / tab strip instead of the edit body. The proven path is now Win32
   ``SetForegroundWindow`` + Alt key-up/key-down foreground-lock
   bypass (``activate_window_by_exact_title_substring``, which
   ``activate_window_by_title_fragment`` delegates to) for focus, and
   HID-level injection via the ``keyboard`` Python lib
   (``send_hotkey_via_keyboard_lib``) for the select-and-copy combo.
2. **Evidence is structured**, not ad-hoc prints. Every smoke writes a
   JSON evidence file under the session evidence dir with the foreign
   app version, fixture path, captured text, and clipboard-restoration
   result. The release reviewer reads these files; the test asserts
   that capture matched and the clipboard was restored.

Patterns
--------

Three patterns cover every surface the maintained smokes drive:

1. **Desktop edit-control apps** (Notepad, Notepad++, VS Code): the
   top-level window foregrounds correctly via Win32, but the title
   bar / tab strip keeps keyboard focus — ``Ctrl+A`` selects nothing
   unless focus is nudged into the document body first. Pattern:
   ``activate_window_by_title_fragment(..., nudge_process_names=(...))``
   for the loose-match helper, or
   ``activate_window_by_exact_title_substring(..., process_names=(...), nudge_process_names=(...))``
   for the process-filtered exact helper VS Code / Notepad++ /
   Windows Terminal smokes use. Both activate helpers accept the
   nudge tuple and fold the click-nudge in via
   ``click_into_window_center`` after a successful Win32 foreground
   swap, then the caller runs ``send_hotkey_via_keyboard_lib("ctrl+a")``
   to drive select-all on the same HID path the capture helper uses
   for Ctrl+C. Default ``nudge_process_names=()`` is bit-identical to
   the pre-#86 / pre-#88 behaviour for callers that don't need a
   nudge (Edge, Edge PDF, Acrobat).
2. **Chromium-based surfaces** (Edge HTML pages, Edge built-in PDF
   viewer): no click-nudge is needed when the fixture publishes a
   readiness marker the harness can wait for. Pattern:
   ``wait_for_edge_selection_ready`` (or
   ``wait_for_edge_pdf_title``) to gate on the renderer being live,
   then ``activate_window_by_title_fragment`` (Edge HTML) or
   ``activate_window_by_exact_title_substring`` (Edge PDF, where
   exact process filtering avoids cross-window matches), then
   ``send_hotkey_via_keyboard_lib("ctrl+a")``. PDF viewers may still
   need a retry-only ``click_into_window_center`` to nudge focus
   from the toolbar into the iframe on cold-start races.
3. **Acrobat-style host-modal PDF readers**: documented ``blocked``
   outcome — Acrobat's first-run / EULA / sign-in modals routinely
   steal focus from the document and ``Ctrl+A`` then lands on the
   modal rather than the page. The smoke records ``blocked`` rather
   than asserting a pass; the reliability matrix tracks the rate.
"""

from __future__ import annotations

import json
import os
import subprocess
import threading
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import pyperclip

# ---------------------------------------------------------------------------
# Engine stub (no real TTS; capture_selection only needs `._capture_lock`).
# ---------------------------------------------------------------------------


class StubCaptureEngine:
    """Minimal stand-in for `pippal.engine.TTSEngine` for capture-only smokes.

    ``capture_selection`` only touches ``engine._capture_lock``, so we
    don't need to drag a real Piper backend into a foreign-app smoke.
    """

    def __init__(self) -> None:
        self._capture_lock = threading.Lock()


# ---------------------------------------------------------------------------
# Evidence record.
# ---------------------------------------------------------------------------


@dataclass
class SmokeEvidence:
    smoke_id: str
    surface: str
    app_path: str
    app_version: str
    fixture_path: str
    expected_text: str
    captured_text: str
    matched_expected: bool
    previous_clipboard_sentinel: str
    clipboard_after_capture: str
    clipboard_restored: bool
    duration_s: float
    extra: dict[str, Any]

    def write(self, evidence_dir: Path) -> Path:
        evidence_dir.mkdir(parents=True, exist_ok=True)
        path = evidence_dir / f"{self.smoke_id}.json"
        path.write_text(json.dumps(asdict(self), indent=2), encoding="utf-8")
        return path


# ---------------------------------------------------------------------------
# Subprocess + foreign-app helpers.
# ---------------------------------------------------------------------------


def run_powershell(script: str, *, timeout: float = 30.0) -> subprocess.CompletedProcess[str]:
    """Run a short PowerShell snippet and return the captured result.

    Uses ``powershell.exe`` (Windows PowerShell 5.1) because it ships
    with every Windows install — we do not require ``pwsh`` for these
    smokes, and the snippets are intentionally tiny.
    """

    return subprocess.run(
        [
            "powershell.exe",
            "-NoProfile",
            "-NonInteractive",
            "-ExecutionPolicy",
            "Bypass",
            "-Command",
            script,
        ],
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )


def get_file_product_version(exe_path: Path) -> str:
    """Resolve the FileVersion field of a Windows binary via PowerShell.

    Used for evidence so the matrix records the exact Notepad / Edge
    build that proved the capture.
    """

    script = (
        f"(Get-Item -LiteralPath '{exe_path}').VersionInfo.FileVersion"
    )
    result = run_powershell(script, timeout=10.0)
    if result.returncode != 0:
        return f"unknown (PowerShell exit {result.returncode})"
    return result.stdout.strip() or "unknown"


def activate_window_by_title_fragment(
    title_fragment: str,
    *,
    attempts: int = 25,
    nudge_process_names: tuple[str, ...] = (),
    nudge_vertical_ratio: float = 0.6,
) -> bool:
    """Bring a window whose title contains ``title_fragment`` to the foreground.

    Originally backed by ``WScript.Shell.AppActivate`` (per the issue
    #57/#58 Notepad repro), this helper now delegates to the Win32
    ``SetForegroundWindow`` path with the Alt-key foreground-lock
    bypass via ``activate_window_by_exact_title_substring``.
    AppActivate's fuzzy matching returns ``True`` when *some*
    window's title shares a token with the requested fragment, even
    if the actually-focused window is unrelated — on a gate machine
    with many windows (Serena Dashboard, other editors) this lets
    Ctrl+A land on the wrong window, silently corrupting the user's
    clipboard. ``activate_window_by_exact_title_substring`` verifies
    ``GetForegroundWindow`` against the target handle before
    returning success, which AppActivate cannot do.

    Title-bar-owns-focus follow-up (issue #84): on modern Win11
    desktop edit-control apps (Notepad as a tabbed UWP-style shell,
    Notepad++, VS Code) the top-level window foregrounds correctly
    but the title bar / tab strip keeps keyboard focus, so a
    follow-up ``Ctrl+A`` selects nothing and the capture comes back
    empty. Pass ``nudge_process_names`` (e.g. ``("notepad",)``) to
    have the helper run ``click_into_window_center`` after a
    successful activation, nudging focus into the document body.
    Default is ``()`` — the helper does nothing extra, so existing
    Chromium / Edge callers are unaffected. ``nudge_vertical_ratio``
    defaults to ``0.6`` so the click lands below the tab strip but
    well inside the text body; tune per app if needed.

    A failed nudge does not flip the overall return value: the
    activation already succeeded, and the call site can run its own
    follow-up click via ``click_into_window_center`` if a specific
    geometry is required (see the PDF / VS Code retry pattern). The
    return value reflects only whether the foreground window swap
    landed on the requested target.
    """

    return activate_window_by_exact_title_substring(
        title_fragment,
        attempts=attempts,
        nudge_process_names=nudge_process_names,
        nudge_vertical_ratio=nudge_vertical_ratio,
    )


def activate_window_by_exact_title_substring(
    title_substring: str,
    *,
    process_names: tuple[str, ...] | None = None,
    attempts: int = 25,
    poll_interval_ms: int = 200,
    nudge_process_names: tuple[str, ...] = (),
    nudge_vertical_ratio: float = 0.6,
) -> bool:
    """Bring the *correct* top-level window matching ``title_substring`` forward.

    ``WScript.Shell.AppActivate`` is fuzzy: when many windows share a
    common token (the gate machine has 15+ Serena Dashboard windows)
    it can latch onto the wrong window even when a perfectly matching
    title exists, and still report success. PDF smokes need exact
    targeting because driving Ctrl+A into the wrong window would
    silently corrupt the user's clipboard.

    This helper uses ``Get-Process`` + ``SetForegroundWindow`` from
    user32, optionally filtered to a specific set of process names
    (e.g. ``("msedge",)`` or ``("Acrobat", "AcroRd32")``). Windows
    blocks foreground stealing from a console-owner process, so we
    first inject a transient Alt key-up/key-down via ``keybd_event``;
    this releases the foreground-lock and lets ``SetForegroundWindow``
    actually move focus to the target window. ``GetForegroundWindow``
    is then checked against the target handle to confirm the focus
    swap actually took effect (Windows can silently flash the taskbar
    instead of stealing focus, so a ``True`` return from
    ``SetForegroundWindow`` is not sufficient evidence on its own).

    Title-bar-owns-focus follow-up (issue #88): the same Win11
    title-bar-keeps-keyboard-focus quirk that motivated the
    ``activate_window_by_title_fragment`` nudge in issue #86 also
    affects callers of the exact-substring helper — VS Code (Electron)
    and Notepad++ both foreground correctly but route ``Ctrl+A`` to
    the title bar / tab strip on first focus. Pass
    ``nudge_process_names`` (e.g. ``("Code",)`` or
    ``("notepad++",)``) to have the helper run
    ``click_into_window_center`` after a successful activation,
    nudging focus into the document body. Default is ``()`` — the
    helper does nothing extra, so existing PDF / Edge / Acrobat
    callers are bit-identical to the pre-#88 behaviour.
    ``nudge_vertical_ratio`` defaults to ``0.6`` to land below the
    tab strip but well inside the text body; tune per app if needed.

    A failed nudge does not flip the overall return value: the
    activation already succeeded, and the call site can run its own
    follow-up click via ``click_into_window_center`` if a specific
    geometry is required. The return value reflects only whether the
    foreground window swap landed on the requested target.
    """

    escaped = title_substring.replace("'", "''")
    if process_names:
        names = ",".join(process_names)
        proc_filter = f"-Name {names} -ErrorAction SilentlyContinue"
    else:
        proc_filter = "-ErrorAction SilentlyContinue"

    script = (
        "Add-Type -Namespace P -Name FG -MemberDefinition @\"\n"
        "[DllImport(\"user32.dll\")] public static extern bool SetForegroundWindow(IntPtr hWnd);\n"
        "[DllImport(\"user32.dll\")] public static extern bool ShowWindow(IntPtr hWnd, int nCmdShow);\n"
        "[DllImport(\"user32.dll\")] public static extern IntPtr GetForegroundWindow();\n"
        "[DllImport(\"user32.dll\")] public static extern void keybd_event("
        "byte bVk, byte bScan, uint dwFlags, int dwExtraInfo);\n"
        "\"@;\n"
        f"for ($i = 0; $i -lt {attempts}; $i++) {{\n"
        f"  $p = Get-Process {proc_filter} | "
        "Where-Object { $_.MainWindowTitle } | "
        f"Where-Object {{ $_.MainWindowTitle -like '*{escaped}*' }} | "
        "Select-Object -First 1;\n"
        "  if ($p) {\n"
        # Send Alt up/down to release the Windows 11 foreground lock
        # that prevents a console-owner process from stealing focus.
        # 0x12 = VK_MENU (Alt), flag 0=keydown, flag 2=keyup.
        "    [P.FG]::keybd_event(0x12, 0, 0, 0);\n"
        "    [P.FG]::keybd_event(0x12, 0, 2, 0);\n"
        "    Start-Sleep -Milliseconds 30;\n"
        "    [P.FG]::ShowWindow($p.MainWindowHandle, 9) | Out-Null;\n"  # SW_RESTORE
        "    [P.FG]::SetForegroundWindow($p.MainWindowHandle) | Out-Null;\n"
        "    Start-Sleep -Milliseconds 200;\n"
        "    if ([P.FG]::GetForegroundWindow() -eq $p.MainWindowHandle) {\n"
        "      Write-Output 'OK'; exit 0;\n"
        "    }\n"
        "  }\n"
        f"  Start-Sleep -Milliseconds {poll_interval_ms};\n"
        "}\n"
        "Write-Output 'MISS'; exit 1"
    )
    result = run_powershell(script, timeout=20.0)
    activated = result.returncode == 0 and "OK" in result.stdout
    if activated and nudge_process_names:
        click_into_window_center(
            title_substring,
            process_names=nudge_process_names,
            vertical_ratio=nudge_vertical_ratio,
        )
    return activated


def send_keys_to_foreground(keys: str, *, settle_s: float = 0.15) -> bool:
    """Send a SendKeys-formatted sequence to the foreground window.

    ``System.Windows.Forms.SendKeys.SendWait`` is the same primitive
    proven to deliver ``^a`` to modern Notepad in the matrix evidence,
    so we keep using it for selection setup.
    """

    escaped = keys.replace("'", "''")
    script = (
        "Add-Type -AssemblyName System.Windows.Forms; "
        f"[System.Windows.Forms.SendKeys]::SendWait('{escaped}'); "
        "Write-Output 'OK'"
    )
    result = run_powershell(script, timeout=10.0)
    time.sleep(settle_s)
    return result.returncode == 0 and "OK" in result.stdout


def send_hotkey_via_keyboard_lib(combo: str, *, settle_s: float = 0.2) -> bool:
    """Send a ``ctrl+a`` / ``ctrl+c`` style combo via the ``keyboard`` lib.

    PowerShell's ``System.Windows.Forms.SendKeys.SendWait`` is enough
    for Notepad and Edge HTML pages, but Edge's built-in PDF viewer
    (a Chromium PDF.js iframe) does not pick up ``^a`` / ``^c`` from
    ``SendKeys`` even when the document area has the foreground.
    The HID-level injection ``keyboard`` uses on Windows reaches the
    iframe the same way a physical key press does. We deliberately
    keep ``send_keys_to_foreground`` as the default for non-PDF
    surfaces — it does not need ``keyboard`` and works on a fresh
    Python install without the optional Windows-only dep.
    """

    try:
        import keyboard
    except Exception:
        return False
    try:
        keyboard.send(combo)
    except Exception:
        return False
    time.sleep(settle_s)
    return True


# ---------------------------------------------------------------------------
# Notepad fixture + driver.
# ---------------------------------------------------------------------------


def launch_notepad(notepad_exe: Path, fixture_path: Path) -> subprocess.Popen[bytes]:
    """Open a known .txt file in Notepad and return the process handle.

    Notepad on Windows 11 may re-use an existing Notepad host (single-
    instance behaviour). That's fine for our smoke: we only need the
    fixture's window title to be reachable via AppActivate.
    """

    return subprocess.Popen([str(notepad_exe), str(fixture_path)])


def notepad_window_title(fixture_path: Path) -> str:
    """Window-title fragment Notepad uses for an opened text file.

    Modern Notepad displays ``<filename>.txt - Notepad`` (or its tab
    title). The basename is enough for AppActivate.
    """

    return fixture_path.name


# ---------------------------------------------------------------------------
# Edge fixture + driver.
# ---------------------------------------------------------------------------


EDGE_READY_SUFFIX = " [PIPPAL_SELECTION_READY]"


EDGE_HTML_TEMPLATE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>{title}</title>
<style>
body {{ font: 16px/1.5 system-ui, sans-serif; margin: 2em; }}
#smoke {{ background: #ffe; padding: 0.5em 1em; border: 1px solid #cc9; }}
</style>
</head>
<body tabindex="-1">
<h1>{title}</h1>
<p id="smoke" tabindex="-1">{sentence}</p>
<script>
(function () {{
  var BASE_TITLE = {title_json};
  var EXPECTED = {sentence_json};
  var READY_SUFFIX = {ready_suffix_json};
  var ready = false;

  function applySelection() {{
    var node = document.getElementById('smoke');
    if (!node) {{ return false; }}
    // Pull keyboard focus into the body so ``Ctrl+C`` lands on the
    // document context (not the omnibox) when Edge's window is just
    // brought to the foreground. Without this, AppActivate may leave
    // focus on a chrome widget on cold start.
    try {{ window.focus(); }} catch (e) {{ /* ignore */ }}
    try {{ document.body.focus(); }} catch (e) {{ /* ignore */ }}
    var sel = window.getSelection();
    if (!sel) {{ return false; }}
    if (sel.toString() === EXPECTED) {{ return true; }}
    var range = document.createRange();
    range.selectNodeContents(node);
    sel.removeAllRanges();
    sel.addRange(range);
    return sel.toString() === EXPECTED;
  }}

  function markReady() {{
    if (ready) {{ return; }}
    ready = true;
    document.body.setAttribute('data-selection-ready', 'true');
    window.__pippalSelectionReady = true;
    document.title = BASE_TITLE + READY_SUFFIX;
  }}

  function tick() {{
    if (applySelection()) {{ markReady(); }}
  }}

  // Re-apply the selection forever at a low cadence so the page is
  // ready for ``Ctrl+C`` even after Edge's omnibox <-> page focus
  // juggling on cold start.
  if (document.readyState === 'complete') {{
    tick();
  }} else {{
    window.addEventListener('load', tick);
  }}
  window.addEventListener('focus', tick, true);
  document.addEventListener('visibilitychange', tick);
  window.setInterval(tick, 50);
}})();
</script>
</body>
</html>
"""


def write_edge_fixture(fixture_dir: Path, title: str, sentence: str) -> Path:
    """Write a self-selecting local HTML fixture and return its path.

    The fixture's inline script re-tries ``window.getSelection()`` until
    the selection matches the expected sentence, then publishes a
    readiness marker by:

    - setting ``document.body[data-selection-ready="true"]``;
    - setting ``window.__pippalSelectionReady = true``;
    - appending ``EDGE_READY_SUFFIX`` to ``document.title``.

    The Python harness polls the window title (via
    ``wait_for_edge_selection_ready``) instead of sleeping, which is
    what the smoke uses to know the renderer has actually applied the
    selection before ``Ctrl+C`` is driven into it.
    """

    fixture_dir.mkdir(parents=True, exist_ok=True)
    html_path = fixture_dir / "edge-selected-text-smoke.html"
    html_path.write_text(
        EDGE_HTML_TEMPLATE.format(
            title=title,
            sentence=sentence,
            title_json=json.dumps(title),
            sentence_json=json.dumps(sentence),
            ready_suffix_json=json.dumps(EDGE_READY_SUFFIX),
        ),
        encoding="utf-8",
    )
    return html_path


def launch_edge(
    edge_exe: Path,
    fixture_html: Path,
    *,
    user_data_dir: Path,
    inprivate: bool = False,
) -> subprocess.Popen[bytes]:
    """Launch Edge with a throwaway profile pointed at the local fixture.

    Using a dedicated ``--user-data-dir`` keeps the smoke off the
    user's real profile (no signed-in account, no extensions, no
    cached state). ``--new-window`` ensures we don't get glued onto
    an already-open Edge instance the user happens to have. Window
    discovery is driven by ``activate_window_by_title_fragment``
    matching against the HTML document's ``<title>``.

    When ``inprivate=True`` the launch adds ``--inprivate``, which
    prevents Edge's sync infobar from intercepting focus when the
    user is signed in to Edge elsewhere on the machine. The HTML
    smoke does not need this because its inline JS keeps re-asserting
    the selection across focus juggling, but the PDF viewer has no
    JS hook to recover from a sync-banner steal — the PDF smoke
    relies on inprivate launches.
    """

    user_data_dir.mkdir(parents=True, exist_ok=True)
    file_url = fixture_html.as_uri()
    args = [
        str(edge_exe),
        f"--user-data-dir={user_data_dir}",
        "--new-window",
        "--no-first-run",
        "--no-default-browser-check",
        "--disable-features=msEdgeWelcomePage,msImplicitSignin",
        "--disable-sync",
    ]
    if inprivate:
        args.append("--inprivate")
    args.append(file_url)
    return subprocess.Popen(args)


def edge_window_title(title: str) -> str:
    """Title fragment Edge uses for a local HTML fixture page.

    Edge prepends the document ``<title>`` to its own chrome label so
    AppActivate matches on the document title alone.
    """

    return title


def wait_for_edge_selection_ready(
    title: str,
    *,
    timeout_s: float = 10.0,
    poll_interval_s: float = 0.1,
) -> bool:
    """Poll Edge's window title until the fixture publishes its readiness marker.

    The local HTML fixture rewrites ``document.title`` to append
    ``EDGE_READY_SUFFIX`` once ``window.getSelection().toString()``
    matches the expected sentence (see ``EDGE_HTML_TEMPLATE``). Edge
    reflects that change into the OS window title, which the Python
    side observes via ``MainWindowTitle`` on the msedge.exe process
    tree — the same primitive ``force_close_notepad_for`` uses.

    Replaces the prior ``time.sleep(0.6)`` settle in the Edge smoke,
    which was the root cause of the cold-start flakiness flagged in
    QA on the second workstation.
    """

    # PowerShell's ``-like`` treats ``[`` and ``]`` as wildcard character
    # classes, so the ``[PIPPAL_SELECTION_READY]`` suffix would never
    # match itself. Use ``-match`` against an escaped regex literal.
    needle = (title + EDGE_READY_SUFFIX).replace("'", "''")
    script = (
        "Get-Process -Name msedge -ErrorAction SilentlyContinue | "
        "Where-Object { $_.MainWindowTitle } | "
        f"Where-Object {{ $_.MainWindowTitle -match [regex]::Escape('{needle}') }} | "
        "Select-Object -First 1 | "
        "ForEach-Object { Write-Output 'READY' }"
    )

    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        result = run_powershell(script, timeout=10.0)
        if result.returncode == 0 and "READY" in result.stdout:
            return True
        time.sleep(poll_interval_s)
    return False


# ---------------------------------------------------------------------------
# Capture-step runner used by all smokes.
# ---------------------------------------------------------------------------


def capture_with_sentinel_clipboard(
    *,
    sentinel: str,
    hotkey_combo: str = "windows+shift+r",
) -> tuple[str, str]:
    """Set the clipboard to a sentinel, invoke ``capture_selection``, and
    report ``(captured_text, clipboard_after_capture)``.

    The sentinel is what was on the clipboard *before* the smoke; the
    capture helper must restore it after reading the foreground app's
    selection. The smoke asserts on both values.
    """

    # Imported lazily because conftest sets up ``sys.path`` before the
    # test session imports modules under test.
    from pippal import clipboard_capture

    pyperclip.copy(sentinel)
    time.sleep(0.05)  # let the clipboard settle

    engine = StubCaptureEngine()
    captured = clipboard_capture.capture_selection(engine, hotkey_combo)

    # Read what is on the clipboard after capture_selection returns. We
    # do NOT poll for restoration — the contract is that capture_selection
    # restores the previous clipboard synchronously before returning.
    try:
        after = pyperclip.paste()
    except Exception:
        after = ""
    return captured, after


def force_close_notepad_for(fixture_path: Path) -> None:
    """Best-effort close of any Notepad window owning ``fixture_path``.

    Notepad on Win11 may prompt on unsaved changes; the smoke writes
    the file content up front and never modifies it, so a graceful
    Stop-Process is safe and avoids leaking processes between smokes.
    """

    script = (
        "Get-Process -Name notepad -ErrorAction SilentlyContinue | "
        "Where-Object { $_.MainWindowTitle -like "
        f"'*{fixture_path.name}*'"
        " } | Stop-Process -Force -ErrorAction SilentlyContinue"
    )
    run_powershell(script, timeout=10.0)


def force_close_edge_user_data_dir(user_data_dir: Path) -> None:
    """Best-effort close of every Edge process bound to ``user_data_dir``.

    Edge child processes carry their ``--user-data-dir`` on the
    command line, so we match on that to avoid killing the user's
    real browser windows.
    """

    path_for_match = str(user_data_dir).replace("\\", "\\\\")
    script = (
        "Get-CimInstance Win32_Process -Filter \"Name = 'msedge.exe'\" | "
        f"Where-Object {{ $_.CommandLine -like '*{path_for_match}*' }} | "
        "ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }"
    )
    run_powershell(script, timeout=10.0)


# ---------------------------------------------------------------------------
# PDF fixture synthesis (issue #63).
# ---------------------------------------------------------------------------


def _pdf_escape(text: str) -> str:
    """Escape a Python string for inclusion in a PDF literal ``(...)``.

    The PDF lexical rules require backslashes and round parens inside a
    literal string to be backslash-escaped. We do not attempt to escape
    non-ASCII here because the fixture sentence is ASCII by contract —
    the smoke is asserting a known fixed sentence round-trips, not
    Unicode handling.
    """

    return text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def write_selectable_text_pdf(fixture_dir: Path, lines: list[str]) -> Path:
    """Synthesise a one-page PDF whose text is selectable by a PDF viewer.

    We use ``pypdf`` to assemble a minimal page with a Helvetica Type1
    font and a single ``BT ... Tj ... ET`` content stream. This avoids
    a new release dependency (``reportlab``) and matches the no-checked-
    in-binaries pattern the existing #62 fixtures use for HTML.

    Each entry in ``lines`` is rendered on its own line via the PDF
    ``T*`` line-advance operator. Splitting the smoke sentence across
    short lines keeps every line well inside the page's selectable
    area in Acrobat and Edge — a single long ``Tj`` that wraps in the
    viewer would silently truncate ``Ctrl+A`` selection to the visible
    region.

    The Acrobat / Edge PDF viewer both extract literal text from
    consecutive ``Tj`` operators and offer it to ``Ctrl+A`` /
    ``Ctrl+C`` as standard PDF text selection. We round-trip via
    ``PdfReader`` only as a sanity check during fixture generation —
    the smoke itself asserts the user-visible capture path.
    """

    from pypdf import PdfReader, PdfWriter
    from pypdf.generic import DictionaryObject, NameObject, StreamObject

    fixture_dir.mkdir(parents=True, exist_ok=True)
    pdf_path = fixture_dir / "pippal_issue63_selectable.pdf"

    writer = PdfWriter()
    page = writer.add_blank_page(width=612, height=792)

    font = DictionaryObject(
        {
            NameObject("/Type"): NameObject("/Font"),
            NameObject("/Subtype"): NameObject("/Type1"),
            NameObject("/BaseFont"): NameObject("/Helvetica"),
            NameObject("/Encoding"): NameObject("/WinAnsiEncoding"),
        }
    )
    font_ref = writer._add_object(font)
    page[NameObject("/Resources")] = DictionaryObject(
        {NameObject("/Font"): DictionaryObject({NameObject("/F1"): font_ref})}
    )

    # We position each line with an absolute ``Td`` rather than relying
    # on ``T*`` line-advance, because some PDF viewers do not consume
    # the text-matrix advance when the leading was set via ``TL`` in
    # the same block. Absolute positioning per line keeps the
    # rendering identical across Acrobat, Edge's PDF.js, and pypdf's
    # own ``extract_text`` round-trip used by the fixture sanity check.
    parts: list[str] = ["BT", "/F1 14 Tf"]
    baseline_top = 720
    line_height = 18
    for index, line in enumerate(lines):
        if index == 0:
            parts.append(f"72 {baseline_top} Td")
        else:
            # ``Td`` is a relative move from the previous text origin.
            parts.append(f"0 -{line_height} Td")
        parts.append(f"({_pdf_escape(line)}) Tj")
    parts.append("ET")
    body = "\n".join(parts) + "\n"

    stream = StreamObject()
    stream._data = body.encode("latin-1")
    page[NameObject("/Contents")] = writer._add_object(stream)

    with pdf_path.open("wb") as fh:
        writer.write(fh)

    # Fixture-generation sanity check (not a substitute for the smoke):
    # if extract_text loses the sentence in synthesis, the smoke would
    # blame the viewer for a bug we introduced in the fixture.
    extracted = PdfReader(str(pdf_path)).pages[0].extract_text() or ""
    for line in lines:
        if line not in extracted:
            raise RuntimeError(
                f"Selectable PDF fixture round-trip failed; pypdf saw "
                f"{extracted!r}, expected to contain {line!r}"
            )
    return pdf_path


def write_image_only_pdf(fixture_dir: Path) -> Path:
    """Synthesise a one-page PDF with no extractable text content layer.

    The page has no ``/Contents`` stream beyond a no-op, so neither
    ``pypdf.extract_text`` nor a PDF viewer's text-layer selection can
    return anything. This simulates a scanned/image-only PDF without
    dragging a real rasterised image into the fixture — the smoke's
    assertion is "no text layer => empty capture, clipboard preserved",
    which the absence of a text content stream is sufficient to prove.
    OCR-style image text is explicitly out of scope until that work
    lands; see ``docs/SELECTED_TEXT_RELIABILITY.md``.
    """

    from pypdf import PdfWriter

    fixture_dir.mkdir(parents=True, exist_ok=True)
    pdf_path = fixture_dir / "pippal_issue63_image_only.pdf"

    writer = PdfWriter()
    writer.add_blank_page(width=612, height=792)
    with pdf_path.open("wb") as fh:
        writer.write(fh)
    return pdf_path


def click_into_window_center(
    title_fragment: str,
    *,
    process_names: tuple[str, ...] = ("msedge", "Acrobat", "AcroRd32"),
    vertical_ratio: float = 0.45,
) -> bool:
    """Move the cursor to and left-click the center of a top-level window.

    Edge's built-in PDF viewer requires the document iframe to hold
    focus before ``Ctrl+A`` reaches the text selection path. Just
    using ``AppActivate`` brings the OS window forward but leaves
    chrome (toolbar / Find) with the focused element. A single
    left-click in the page center reliably moves focus into the
    Chromium PDF viewer plugin's document area.

    The same pattern is needed for modern Notepad on Win11 (issue #84):
    after ``activate_window_by_exact_title_substring`` brings the
    top-level window forward, the title-bar / tab strip still owns
    keyboard focus, not the edit child — so ``Ctrl+A`` does not
    select anything. A click in the document area moves focus into
    the edit control. Pass ``process_names=("notepad",)`` and a
    larger ``vertical_ratio`` (e.g. ``0.6``) to land below the tab
    strip but still inside the text body.

    Implemented via ``user32`` ``SetCursorPos`` + ``mouse_event`` from
    PowerShell so we do not add a new Python dependency.
    """

    escaped = title_fragment.replace("'", "''")
    names = ",".join(process_names)
    script = (
        "Add-Type -Namespace P -Name Win -MemberDefinition @\"\n"
        "[DllImport(\"user32.dll\")] public static extern bool SetCursorPos(int X, int Y);\n"
        "[DllImport(\"user32.dll\")] public static extern void mouse_event("
        "uint dwFlags, uint dx, uint dy, uint dwData, int dwExtraInfo);\n"
        "[StructLayout(LayoutKind.Sequential)] public struct RECT { public int L, T, R, B; }\n"
        "[DllImport(\"user32.dll\")] public static extern bool GetWindowRect(IntPtr hWnd, out RECT lpRect);\n"
        "\"@;\n"
        f"$proc = Get-Process -Name {names} -ErrorAction SilentlyContinue | "
        f"Where-Object {{ $_.MainWindowTitle -like '*{escaped}*' }} | Select-Object -First 1;\n"
        "if (-not $proc) { Write-Output 'NOWINDOW'; exit 1 }\n"
        "$rect = New-Object P.Win+RECT;\n"
        "[P.Win]::GetWindowRect($proc.MainWindowHandle, [ref] $rect) | Out-Null;\n"
        "$cx = [int](($rect.L + $rect.R) / 2);\n"
        f"$cy = [int]($rect.T + (($rect.B - $rect.T) * {vertical_ratio}));\n"
        "[P.Win]::SetCursorPos($cx, $cy) | Out-Null;\n"
        "[P.Win]::mouse_event(0x0002, 0, 0, 0, 0);\n"  # LEFTDOWN
        "Start-Sleep -Milliseconds 50;\n"
        "[P.Win]::mouse_event(0x0004, 0, 0, 0, 0);\n"  # LEFTUP
        "Write-Output 'CLICKED'"
    )
    result = run_powershell(script, timeout=15.0)
    return result.returncode == 0 and "CLICKED" in result.stdout


def wait_for_edge_pdf_title(
    pdf_path: Path,
    *,
    timeout_s: float = 15.0,
    poll_interval_s: float = 0.2,
) -> bool:
    """Poll until an msedge.exe window's title contains the PDF basename.

    Edge's built-in PDF viewer takes noticeably longer to paint than
    an HTML page because PDF.js streams the document and only then
    sets the document title to the filename. Without this wait, the
    happy-path smoke races ``Ctrl+A`` against a sync infobar that
    Edge sometimes briefly pops over the page; once the PDF title is
    in the OS window list we know the viewer has reached the page-
    rendered state.
    """

    needle = pdf_path.stem.replace("'", "''")
    script = (
        "Get-Process -Name msedge -ErrorAction SilentlyContinue | "
        "Where-Object { $_.MainWindowTitle } | "
        f"Where-Object {{ $_.MainWindowTitle -like '*{needle}*' }} | "
        "Select-Object -First 1 | "
        "ForEach-Object { Write-Output 'READY' }"
    )
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        result = run_powershell(script, timeout=10.0)
        if result.returncode == 0 and "READY" in result.stdout:
            return True
        time.sleep(poll_interval_s)
    return False


def edge_pdf_window_title(pdf_path: Path) -> str:
    """Window-title fragment Edge uses for an opened local PDF.

    Edge's built-in PDF viewer titles the window with the PDF basename;
    AppActivate matches on the basename *stem* (without the ``.pdf``
    suffix) because ``WScript.Shell.AppActivate`` treats the trailing
    ``.pdf`` as a wildcard-stop and returns ``False`` for any title
    fragment containing a literal extension. Using the stem keeps
    AppActivate reachable while still being unique enough to find the
    fixture's window.
    """

    return pdf_path.stem


# ---------------------------------------------------------------------------
# Acrobat / Adobe Reader driver (issue #63).
# ---------------------------------------------------------------------------


ACROBAT_CANDIDATES: tuple[Path, ...] = (
    Path(r"C:\Program Files\Adobe\Acrobat DC\Acrobat\Acrobat.exe"),
    Path(r"C:\Program Files (x86)\Adobe\Acrobat Reader DC\Reader\AcroRd32.exe"),
    Path(r"C:\Program Files\Adobe\Acrobat DC\Acrobat\AcroRd32.exe"),
    Path(r"C:\Program Files (x86)\Adobe\Acrobat DC\Acrobat\Acrobat.exe"),
)


def find_acrobat_exe() -> Path | None:
    """Locate an installed Acrobat or Adobe Reader executable.

    Returns ``None`` when neither is installed; the caller records that
    case as ``unavailable`` (per the shared release-gate status contract)
    rather than failing the smoke. This is the same pattern Notepad/Edge
    detection uses in ``conftest.py``.
    """

    for candidate in ACROBAT_CANDIDATES:
        if candidate.is_file():
            return candidate
    return None


def launch_acrobat(acrobat_exe: Path, fixture_pdf: Path) -> subprocess.Popen[bytes]:
    """Open a PDF in Acrobat / Adobe Reader and return the process handle.

    Acrobat is single-instance on Windows: a second launch typically
    forwards the file to the running process and the new ``Popen``
    exits quickly. The smoke only needs the file to be open in a
    window whose title contains the PDF basename, which AppActivate
    can latch onto regardless of which Acrobat process owns it.
    """

    return subprocess.Popen([str(acrobat_exe), str(fixture_pdf)])


def acrobat_window_title(pdf_path: Path) -> str:
    """Window-title fragment Acrobat uses for an opened PDF.

    Acrobat appends the document filename to its chrome label. We
    return the basename *stem* without ``.pdf`` so
    ``WScript.Shell.AppActivate`` matches it — AppActivate returns
    ``False`` for any title fragment containing a literal extension,
    so a fragment of ``foo.pdf`` would never focus the Acrobat
    window even though the OS title contains exactly that substring.
    """

    return pdf_path.stem


def wait_for_acrobat_title(
    pdf_path: Path,
    *,
    timeout_s: float = 25.0,
    poll_interval_s: float = 0.3,
) -> bool:
    """Poll until Acrobat publishes a window title containing the PDF stem.

    Acrobat cold-start is markedly slower than Edge's PDF viewer: a
    ``Welcome`` / ``Sign in`` modal or a license-renewal pane can hold
    the foreground for several seconds, during which the document
    window has no title at all. ``MainWindowTitle`` stays empty in
    that window — AppActivate would silently fail and the smoke would
    record empty captures forever. Polling for the titled document
    window lets the smoke distinguish "Acrobat is unhealthy on this
    box, mark blocked" from "Acrobat captured wrong text, mark fail".
    """

    needle = pdf_path.stem.replace("'", "''")
    script = (
        "Get-Process -Name Acrobat,AcroRd32 -ErrorAction SilentlyContinue | "
        "Where-Object { $_.MainWindowTitle } | "
        f"Where-Object {{ $_.MainWindowTitle -like '*{needle}*' }} | "
        "Select-Object -First 1 | "
        "ForEach-Object { Write-Output 'READY' }"
    )
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        result = run_powershell(script, timeout=10.0)
        if result.returncode == 0 and "READY" in result.stdout:
            return True
        time.sleep(poll_interval_s)
    return False


def force_close_acrobat_for(pdf_path: Path) -> None:
    """Best-effort close of any Acrobat window owning ``pdf_path``.

    Matches on either ``Acrobat.exe`` or ``AcroRd32.exe`` with a window
    title containing the fixture basename, to avoid touching another
    Acrobat document the user might have open during the smoke run.
    """

    needle = pdf_path.name.replace("'", "''")
    script = (
        "Get-Process -Name Acrobat,AcroRd32 -ErrorAction SilentlyContinue | "
        f"Where-Object {{ $_.MainWindowTitle -like '*{needle}*' }} | "
        "Stop-Process -Force -ErrorAction SilentlyContinue"
    )
    run_powershell(script, timeout=10.0)


def write_initial_clipboard(value: str) -> None:
    pyperclip.copy(value)
    time.sleep(0.05)


# ---------------------------------------------------------------------------
# Editor / terminal / chat driver helpers (issue #61).
# ---------------------------------------------------------------------------


VSCODE_CANDIDATES: tuple[Path, ...] = (
    Path(
        r"C:\Users\tigyi\AppData\Local\Programs\Microsoft VS Code\Code.exe"
    ),
    Path(r"C:\Program Files\Microsoft VS Code\Code.exe"),
    Path(r"C:\Program Files (x86)\Microsoft VS Code\Code.exe"),
)


NOTEPAD_PP_CANDIDATES: tuple[Path, ...] = (
    Path(r"C:\Program Files\Notepad++\notepad++.exe"),
    Path(r"C:\Program Files (x86)\Notepad++\notepad++.exe"),
)


OUTLOOK_CANDIDATES: tuple[Path, ...] = (
    Path(r"C:\Program Files\Microsoft Office\root\Office16\OUTLOOK.EXE"),
    Path(r"C:\Program Files (x86)\Microsoft Office\root\Office16\OUTLOOK.EXE"),
)


TEAMS_CANDIDATES: tuple[Path, ...] = (
    Path(r"C:\Users\tigyi\AppData\Local\Microsoft\WindowsApps\ms-teams.exe"),
)


DISCORD_CANDIDATES: tuple[Path, ...] = (
    Path(r"C:\Users\tigyi\AppData\Local\Discord"),
)


def find_vscode_exe() -> Path | None:
    """Locate an installed VS Code executable, or ``None``.

    Returns ``None`` when no install is found; the editor smoke records
    that as ``unavailable`` per the shared release-gate status contract.
    """

    import shutil

    which = shutil.which("code.exe")
    if which and Path(which).is_file():
        return Path(which)
    for candidate in VSCODE_CANDIDATES:
        if candidate.is_file():
            return candidate
    return None


def find_notepad_pp_exe() -> Path | None:
    """Locate an installed Notepad++ executable, or ``None``."""

    import shutil

    which = shutil.which("notepad++.exe")
    if which and Path(which).is_file():
        return Path(which)
    for candidate in NOTEPAD_PP_CANDIDATES:
        if candidate.is_file():
            return candidate
    return None


def find_windows_terminal_exe() -> Path | None:
    """Locate the Windows Terminal launcher (``wt.exe``), or ``None``.

    Windows Terminal is distributed as an Appx package; ``wt.exe`` is a
    Store-shim that lives under ``%LOCALAPPDATA%\\Microsoft\\WindowsApps``.
    The shim is the documented programmatic launch path — it dispatches
    into the actual ``WindowsTerminal.exe`` inside the Appx package.
    """

    import shutil

    which = shutil.which("wt.exe")
    if which and Path(which).is_file():
        return Path(which)
    candidate = Path(
        r"C:\Users\tigyi\AppData\Local\Microsoft\WindowsApps\wt.exe"
    )
    if candidate.is_file():
        return candidate
    return None


def find_powershell_exe() -> Path | None:
    """Locate ``powershell.exe`` (Windows PowerShell 5.1 legacy console).

    The conhost-hosted Windows PowerShell ships on every Windows install
    and is the documented fallback when Windows Terminal is not present.
    """

    candidate = Path(r"C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe")
    if candidate.is_file():
        return candidate
    return None


def find_outlook_exe() -> Path | None:
    """Locate ``OUTLOOK.EXE``, or ``None``."""

    import shutil

    which = shutil.which("outlook.exe")
    if which and Path(which).is_file():
        return Path(which)
    for candidate in OUTLOOK_CANDIDATES:
        if candidate.is_file():
            return candidate
    return None


def find_teams_exe() -> Path | None:
    """Locate the new Teams (Store) Win32 shim, or ``None``.

    The current ("new") Teams client is an Appx package; ``ms-teams.exe``
    is the Store shim that ``%LOCALAPPDATA%\\Microsoft\\WindowsApps``
    publishes for programmatic launch.
    """

    import shutil

    which = shutil.which("ms-teams.exe")
    if which and Path(which).is_file():
        return Path(which)
    for candidate in TEAMS_CANDIDATES:
        if candidate.is_file():
            return candidate
    return None


def find_discord_exe() -> Path | None:
    """Locate a Discord install, or ``None``.

    Discord ships as a per-user installer; the launcher lives at
    ``%LOCALAPPDATA%\\Discord\\app-<version>\\Discord.exe`` with the
    version baked into the directory name (squirrel pattern). We glob
    the parent dir and pick the most recent install if multiple are
    present.
    """

    parent = Path(r"C:\Users\tigyi\AppData\Local\Discord")
    if not parent.is_dir():
        return None
    matches = sorted(parent.glob("app-*/Discord.exe"), reverse=True)
    return matches[0] if matches else None


def launch_vscode(
    vscode_exe: Path,
    fixture_path: Path,
    *,
    user_data_dir: Path,
    extensions_dir: Path,
) -> subprocess.Popen[bytes]:
    """Open a fixture file in a clean VS Code instance and return the process.

    ``--user-data-dir`` and ``--extensions-dir`` point at throwaway dirs
    so the smoke never touches the user's real VS Code profile (no
    signed-in account, no extensions, no recently-opened file list).
    ``-n`` forces a new window so we don't get glued onto an already-
    open VS Code instance the user happens to have running. ``--wait``
    is intentionally omitted: VS Code returns immediately after the
    window is requested, and the smoke polls for the window title
    rather than blocking on the editor process exit.
    """

    user_data_dir.mkdir(parents=True, exist_ok=True)
    extensions_dir.mkdir(parents=True, exist_ok=True)
    args = [
        str(vscode_exe),
        "-n",
        "--disable-extensions",
        f"--user-data-dir={user_data_dir}",
        f"--extensions-dir={extensions_dir}",
        "--skip-release-notes",
        "--skip-welcome",
        str(fixture_path),
    ]
    return subprocess.Popen(args)


def vscode_window_title(fixture_path: Path) -> str:
    """Window-title fragment VS Code uses for an opened file.

    VS Code titles its window ``<basename> - <foldername> - Visual Studio
    Code``. The basename alone is enough for the exact-substring
    activator scoped to the ``Code`` process name.
    """

    return fixture_path.name


def wait_for_vscode_title(
    fixture_path: Path,
    *,
    timeout_s: float = 25.0,
    poll_interval_s: float = 0.3,
) -> bool:
    """Poll until a Code.exe process publishes a title containing the file name."""

    needle = fixture_path.name.replace("'", "''")
    script = (
        "Get-Process -Name Code -ErrorAction SilentlyContinue | "
        "Where-Object { $_.MainWindowTitle } | "
        f"Where-Object {{ $_.MainWindowTitle -like '*{needle}*' }} | "
        "Select-Object -First 1 | "
        "ForEach-Object { Write-Output 'READY' }"
    )
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        result = run_powershell(script, timeout=10.0)
        if result.returncode == 0 and "READY" in result.stdout:
            return True
        time.sleep(poll_interval_s)
    return False


def force_close_vscode_for(user_data_dir: Path) -> None:
    """Best-effort close of any Code.exe process bound to ``user_data_dir``.

    Mirrors ``force_close_edge_user_data_dir`` — Code's child processes
    carry the ``--user-data-dir`` argument on the command line so the
    match cannot accidentally hit the user's real VS Code windows.
    """

    path_for_match = str(user_data_dir).replace("\\", "\\\\")
    script = (
        "Get-CimInstance Win32_Process -Filter \"Name = 'Code.exe'\" | "
        f"Where-Object {{ $_.CommandLine -like '*{path_for_match}*' }} | "
        "ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }"
    )
    run_powershell(script, timeout=10.0)


def launch_windows_terminal(
    wt_exe: Path,
    *,
    title: str,
    inline_command: str,
) -> subprocess.Popen[bytes]:
    """Open a Windows Terminal tab running ``inline_command`` under pwsh -NoExit.

    ``--title`` is the documented ``wt`` flag for forcing the tab title,
    which our window-activation helper relies on for exact targeting.
    ``-NoExit`` keeps the shell open after the inline command emits the
    fixture text, so the buffer content stays selectable until the
    smoke is finished.
    """

    pwsh = Path(r"C:\Program Files\PowerShell\7\pwsh.exe")
    if not pwsh.is_file():
        # Fallback: Windows PowerShell 5.1 (always present). Same -NoExit /
        # -Command surface so the inline_command works identically.
        pwsh = Path(r"C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe")
    args = [
        str(wt_exe),
        "--window",
        "new",
        "--title",
        title,
        str(pwsh),
        "-NoLogo",
        "-NoProfile",
        "-NoExit",
        "-Command",
        inline_command,
    ]
    return subprocess.Popen(args)


def wait_for_windows_terminal_title(
    title: str,
    *,
    timeout_s: float = 30.0,
    poll_interval_s: float = 0.25,
) -> bool:
    """Poll until a Windows Terminal window publishes the requested title.

    The Windows Terminal host process is ``WindowsTerminal.exe``; the
    ``wt.exe`` shim exits as soon as it has dispatched into the host.
    We match on the host so we do not race the shim's exit.
    """

    escaped = title.replace("'", "''")
    script = (
        "Get-Process -Name WindowsTerminal -ErrorAction SilentlyContinue | "
        "Where-Object { $_.MainWindowTitle } | "
        f"Where-Object {{ $_.MainWindowTitle -like '*{escaped}*' }} | "
        "Select-Object -First 1 | "
        "ForEach-Object { Write-Output 'READY' }"
    )
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        result = run_powershell(script, timeout=10.0)
        if result.returncode == 0 and "READY" in result.stdout:
            return True
        time.sleep(poll_interval_s)
    return False


def force_close_windows_terminal_for(title: str) -> None:
    """Best-effort close of Windows Terminal windows with the given title."""

    escaped = title.replace("'", "''")
    script = (
        "Get-Process -Name WindowsTerminal -ErrorAction SilentlyContinue | "
        f"Where-Object {{ $_.MainWindowTitle -like '*{escaped}*' }} | "
        "Stop-Process -Force -ErrorAction SilentlyContinue"
    )
    run_powershell(script, timeout=10.0)


# Public re-exports for tests.
__all__ = [
    "ACROBAT_CANDIDATES",
    "DISCORD_CANDIDATES",
    "EDGE_HTML_TEMPLATE",
    "EDGE_READY_SUFFIX",
    "NOTEPAD_PP_CANDIDATES",
    "OUTLOOK_CANDIDATES",
    "TEAMS_CANDIDATES",
    "VSCODE_CANDIDATES",
    "SmokeEvidence",
    "StubCaptureEngine",
    "acrobat_window_title",
    "activate_window_by_exact_title_substring",
    "activate_window_by_title_fragment",
    "capture_with_sentinel_clipboard",
    "click_into_window_center",
    "edge_pdf_window_title",
    "edge_window_title",
    "find_acrobat_exe",
    "find_discord_exe",
    "find_notepad_pp_exe",
    "find_outlook_exe",
    "find_powershell_exe",
    "find_teams_exe",
    "find_vscode_exe",
    "find_windows_terminal_exe",
    "force_close_acrobat_for",
    "force_close_edge_user_data_dir",
    "force_close_notepad_for",
    "force_close_vscode_for",
    "force_close_windows_terminal_for",
    "get_file_product_version",
    "launch_acrobat",
    "launch_edge",
    "launch_notepad",
    "launch_vscode",
    "launch_windows_terminal",
    "notepad_window_title",
    "run_powershell",
    "send_hotkey_via_keyboard_lib",
    "send_keys_to_foreground",
    "vscode_window_title",
    "wait_for_acrobat_title",
    "wait_for_edge_pdf_title",
    "wait_for_edge_selection_ready",
    "wait_for_vscode_title",
    "wait_for_windows_terminal_title",
    "write_edge_fixture",
    "write_image_only_pdf",
    "write_initial_clipboard",
    "write_selectable_text_pdf",
]


def _selftest_imports() -> None:
    """Imported helpers are usable on this machine.

    This is intentionally not a pytest test; it is a tiny ``__main__``
    sanity check used by the runner script so a configuration mistake
    (missing pyperclip backend, missing PowerShell) fails fast before
    we open any foreign-app window.
    """

    pyperclip.copy("__pippal_ui_smoke_selftest__")
    if pyperclip.paste() != "__pippal_ui_smoke_selftest__":
        raise SystemExit("pyperclip clipboard round-trip failed")
    result = run_powershell("Write-Output 'OK'", timeout=10.0)
    if result.returncode != 0 or "OK" not in result.stdout:
        raise SystemExit(f"powershell.exe not usable: {result.returncode} {result.stderr!r}")


if __name__ == "__main__":  # pragma: no cover - operator entry point
    _selftest_imports()
    print("ui-smokes harness selftest OK", flush=True)
    os._exit(0)
