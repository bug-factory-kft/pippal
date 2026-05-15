"""Foreign-app driver helpers for the maintained selected-text UI smokes.

This module is the *small* extension of the existing live UI evidence
gate (`e2e/`) — it does not replace it. The live UI gate proves the
PipPal desktop app's own widgets; these smokes prove the source
``pippal.clipboard_capture.capture_selection`` helper against a foreign
app (Notepad / Edge) that the user actually selects text in.

Two design rules:

1. **Selection must be set up by an external proven path**, not by the
   capture helper itself. We use ``WScript.Shell.AppActivate`` for
   focus and ``System.Windows.Forms.SendKeys.SendWait('^a')`` for the
   selection, because the issue #57 / #58 repro evidence in
   ``docs/SELECTED_TEXT_RELIABILITY.md`` already proves they work on
   modern Notepad on Win11.
2. **Evidence is structured**, not ad-hoc prints. Every smoke writes a
   JSON evidence file under the session evidence dir with the foreign
   app version, fixture path, captured text, and clipboard-restoration
   result. The release reviewer reads these files; the test asserts
   that capture matched and the clipboard was restored.
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


def activate_window_by_title_fragment(title_fragment: str, *, attempts: int = 25) -> bool:
    """Bring a window whose title contains ``title_fragment`` to the foreground.

    Uses ``WScript.Shell.AppActivate`` because it is the same focus
    primitive that worked in the issue #57/#58 Notepad repro
    documented in ``docs/SELECTED_TEXT_RELIABILITY.md``.
    """

    escaped = title_fragment.replace("'", "''")
    script = (
        "$ws = New-Object -ComObject WScript.Shell; "
        f"for ($i = 0; $i -lt {attempts}; $i++) {{"
        f"  if ($ws.AppActivate('{escaped}')) {{ Write-Output 'OK'; exit 0 }}"
        "  Start-Sleep -Milliseconds 200"
        "} ; "
        "Write-Output 'MISS'; exit 1"
    )
    result = run_powershell(script, timeout=15.0)
    return result.returncode == 0 and "OK" in result.stdout


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
<body>
<h1>{title}</h1>
<p id="smoke">{sentence}</p>
<script>
window.addEventListener('load', function () {{
  var node = document.getElementById('smoke');
  var range = document.createRange();
  range.selectNodeContents(node);
  var sel = window.getSelection();
  sel.removeAllRanges();
  sel.addRange(range);
}});
</script>
</body>
</html>
"""


def write_edge_fixture(fixture_dir: Path, title: str, sentence: str) -> Path:
    """Write a self-selecting local HTML fixture and return its path."""

    fixture_dir.mkdir(parents=True, exist_ok=True)
    html_path = fixture_dir / "edge-selected-text-smoke.html"
    html_path.write_text(
        EDGE_HTML_TEMPLATE.format(title=title, sentence=sentence),
        encoding="utf-8",
    )
    return html_path


def launch_edge(
    edge_exe: Path,
    fixture_html: Path,
    *,
    user_data_dir: Path,
    title: str,
) -> subprocess.Popen[bytes]:
    """Launch Edge with a throwaway profile pointed at the local fixture.

    Using a dedicated ``--user-data-dir`` keeps the smoke off the
    user's real profile (no signed-in account, no extensions, no
    cached state). ``--new-window`` ensures we don't get glued onto
    an already-open Edge instance the user happens to have.
    """

    user_data_dir.mkdir(parents=True, exist_ok=True)
    file_url = fixture_html.as_uri()
    return subprocess.Popen(
        [
            str(edge_exe),
            f"--user-data-dir={user_data_dir}",
            "--new-window",
            "--no-first-run",
            "--no-default-browser-check",
            "--disable-features=msEdgeWelcomePage",
            f"--window-name={title}",
            file_url,
        ]
    )


def edge_window_title(title: str) -> str:
    """Title fragment Edge uses for a local HTML fixture page.

    Edge prepends the document ``<title>`` to its own chrome label so
    AppActivate matches on the document title alone.
    """

    return title


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


def write_initial_clipboard(value: str) -> None:
    pyperclip.copy(value)
    time.sleep(0.05)


# Public re-exports for tests.
__all__ = [
    "EDGE_HTML_TEMPLATE",
    "SmokeEvidence",
    "StubCaptureEngine",
    "activate_window_by_title_fragment",
    "capture_with_sentinel_clipboard",
    "edge_window_title",
    "force_close_edge_user_data_dir",
    "force_close_notepad_for",
    "get_file_product_version",
    "launch_edge",
    "launch_notepad",
    "notepad_window_title",
    "run_powershell",
    "send_keys_to_foreground",
    "write_edge_fixture",
    "write_initial_clipboard",
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
