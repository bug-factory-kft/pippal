"""Maintained selected-text UI smokes for Notepad and Edge (issue #62).

These tests are the maintained companions to the manual repro evidence
recorded in ``docs/SELECTED_TEXT_RELIABILITY.md``. They exist so that
the v0.2.5 release gate is *not* tribal knowledge: a release reviewer
runs ``e2e/run-ui-smokes.ps1`` and either gets a green ``pass`` JSON
summary or sees exactly which surface broke.

Coverage:

- Notepad happy path: select-all in a temp .txt fixture, capture, assert
  captured text matches and the previous clipboard is restored.
- Notepad known-bad-state recovery: focus a Notepad window with no
  selection, capture, assert empty result *and* clipboard sentinel
  preserved (the capture helper must never clobber the user's clipboard
  even when the foreign app has nothing to copy).
- Edge browser happy path: open a local HTML fixture that DOM-selects a
  known paragraph, capture, assert captured text matches and the
  previous clipboard is restored.

Out of scope here (issue #62 is "Notepad + one Chromium browser"):
PDF surfaces (#63), editor/terminal/chat surfaces (#61), elevated apps,
and human-driven installed-app global-hotkey confirmation.
"""

from __future__ import annotations

import time
from pathlib import Path

import pytest

from . import _harness as harness

pytestmark = pytest.mark.ui_smoke


NOTEPAD_TEXT = (
    "PipPal issue 62 Notepad selected-text smoke: capture_selection must "
    "copy this exact sentence and restore the previous clipboard."
)

NOTEPAD_SENTINEL_HAPPY = "ISSUE62_NOTEPAD_HAPPY_PREVIOUS_CLIPBOARD"
NOTEPAD_SENTINEL_RECOVERY = "ISSUE62_NOTEPAD_RECOVERY_PREVIOUS_CLIPBOARD"

EDGE_TITLE = "PipPal Issue 62 Browser Smoke"
EDGE_TEXT = (
    "PipPal issue 62 Edge browser selected-text smoke: capture_selection "
    "must copy this exact browser sentence and restore the previous clipboard."
)
EDGE_SENTINEL = "ISSUE62_EDGE_PREVIOUS_CLIPBOARD"


# ---------------------------------------------------------------------------
# Notepad smokes.
# ---------------------------------------------------------------------------


def test_notepad_selected_text_happy_path(
    notepad_exe: Path,
    evidence_dir: Path,
    tmp_path_factory: pytest.TempPathFactory,
) -> None:
    fixture_dir = tmp_path_factory.mktemp("pippal_issue62_notepad_happy")
    fixture_path = fixture_dir / "pippal_issue62_notepad_happy.txt"
    fixture_path.write_text(NOTEPAD_TEXT, encoding="utf-8")

    app_version = harness.get_file_product_version(notepad_exe)
    process = harness.launch_notepad(notepad_exe, fixture_path)
    started = time.monotonic()
    try:
        focused = harness.activate_window_by_title_fragment(
            harness.notepad_window_title(fixture_path)
        )
        assert focused, (
            f"Notepad window for {fixture_path.name} did not accept focus; "
            "another modal window may be in the foreground"
        )

        selected = harness.send_keys_to_foreground("^a")
        assert selected, "SendKeys ^a (select-all) into Notepad failed"

        # Settle: give Notepad a tick to actually render the selection
        # before the capture helper drives Ctrl+C against it.
        time.sleep(0.2)

        captured, clipboard_after = harness.capture_with_sentinel_clipboard(
            sentinel=NOTEPAD_SENTINEL_HAPPY,
        )

        evidence = harness.SmokeEvidence(
            smoke_id="notepad_selected_text_happy_path",
            surface="Notepad plain text",
            app_path=str(notepad_exe),
            app_version=app_version,
            fixture_path=str(fixture_path),
            expected_text=NOTEPAD_TEXT,
            captured_text=captured,
            matched_expected=(captured == NOTEPAD_TEXT),
            previous_clipboard_sentinel=NOTEPAD_SENTINEL_HAPPY,
            clipboard_after_capture=clipboard_after,
            clipboard_restored=(clipboard_after == NOTEPAD_SENTINEL_HAPPY),
            duration_s=time.monotonic() - started,
            extra={"selection_method": "SendKeys ^a", "focus_method": "AppActivate"},
        )
        evidence.write(evidence_dir)

        assert captured == NOTEPAD_TEXT, (
            f"Notepad capture mismatch.\n"
            f"  expected: {NOTEPAD_TEXT!r}\n"
            f"  captured: {captured!r}\n"
            f"  app: {notepad_exe} ({app_version})"
        )
        assert clipboard_after == NOTEPAD_SENTINEL_HAPPY, (
            "Notepad smoke left the clipboard unrestored. "
            f"expected sentinel {NOTEPAD_SENTINEL_HAPPY!r}, "
            f"clipboard now {clipboard_after!r}. "
            "This is a Core capture bug — the user's clipboard must survive a read."
        )
    finally:
        try:
            process.terminate()
        except Exception:
            pass
        harness.force_close_notepad_for(fixture_path)


def test_notepad_no_selection_recovery_path(
    notepad_exe: Path,
    evidence_dir: Path,
    tmp_path_factory: pytest.TempPathFactory,
) -> None:
    """Known-bad-state recovery: Notepad focused, *nothing* selected.

    Real users hit this whenever they press the read-selection hotkey
    after clicking into a window without highlighting anything. The
    contract is:

    - ``capture_selection`` returns an empty string (no garbage text);
    - the user's previous clipboard is fully restored — Core must never
      destroy clipboard contents when the foreground app has nothing
      to copy.
    """

    fixture_dir = tmp_path_factory.mktemp("pippal_issue62_notepad_recovery")
    fixture_path = fixture_dir / "pippal_issue62_notepad_recovery.txt"
    fixture_path.write_text(NOTEPAD_TEXT, encoding="utf-8")

    app_version = harness.get_file_product_version(notepad_exe)
    process = harness.launch_notepad(notepad_exe, fixture_path)
    started = time.monotonic()
    try:
        focused = harness.activate_window_by_title_fragment(
            harness.notepad_window_title(fixture_path)
        )
        assert focused, (
            f"Notepad window for {fixture_path.name} did not accept focus"
        )

        # Deliberately collapse any prior selection: send End then Home so
        # the caret sits at column 0 with no range selected. This is the
        # "known-bad-state" the smoke is asserting against.
        cleared = harness.send_keys_to_foreground("{END}{HOME}")
        assert cleared, "SendKeys to clear selection in Notepad failed"
        time.sleep(0.2)

        captured, clipboard_after = harness.capture_with_sentinel_clipboard(
            sentinel=NOTEPAD_SENTINEL_RECOVERY,
        )

        evidence = harness.SmokeEvidence(
            smoke_id="notepad_no_selection_recovery_path",
            surface="Notepad plain text, no selection",
            app_path=str(notepad_exe),
            app_version=app_version,
            fixture_path=str(fixture_path),
            expected_text="",
            captured_text=captured,
            matched_expected=(captured == ""),
            previous_clipboard_sentinel=NOTEPAD_SENTINEL_RECOVERY,
            clipboard_after_capture=clipboard_after,
            clipboard_restored=(clipboard_after == NOTEPAD_SENTINEL_RECOVERY),
            duration_s=time.monotonic() - started,
            extra={
                "selection_method": "SendKeys {END}{HOME} to collapse caret",
                "focus_method": "AppActivate",
                "rationale": (
                    "User pressed read-selection hotkey without selecting "
                    "text; capture helper must return empty and preserve "
                    "the prior clipboard."
                ),
            },
        )
        evidence.write(evidence_dir)

        assert captured == "", (
            "Notepad no-selection capture leaked text. capture_selection "
            f"returned {captured!r}; expected empty string."
        )
        assert clipboard_after == NOTEPAD_SENTINEL_RECOVERY, (
            "Notepad no-selection smoke clobbered the clipboard. "
            f"expected sentinel {NOTEPAD_SENTINEL_RECOVERY!r}, "
            f"clipboard now {clipboard_after!r}. "
            "Core must restore the previous clipboard even on empty captures."
        )
    finally:
        try:
            process.terminate()
        except Exception:
            pass
        harness.force_close_notepad_for(fixture_path)


# ---------------------------------------------------------------------------
# Edge browser smoke.
# ---------------------------------------------------------------------------


def test_edge_webpage_selected_text_happy_path(
    edge_exe: Path,
    evidence_dir: Path,
    tmp_path_factory: pytest.TempPathFactory,
) -> None:
    fixture_dir = tmp_path_factory.mktemp("pippal_issue62_edge")
    user_data_dir = fixture_dir / "edge-profile"
    fixture_html = harness.write_edge_fixture(fixture_dir, EDGE_TITLE, EDGE_TEXT)

    app_version = harness.get_file_product_version(edge_exe)
    process = harness.launch_edge(
        edge_exe,
        fixture_html,
        user_data_dir=user_data_dir,
    )
    started = time.monotonic()
    try:
        # Wait for the fixture's JS to publish a selection-ready marker
        # by appending ``EDGE_READY_SUFFIX`` to ``document.title``. The
        # poll uses the msedge.exe ``MainWindowTitle``, so it does not
        # depend on the window being focused. This replaces the prior
        # ``time.sleep(0.6)`` settle that was the root cause of cold-
        # start flakiness in QA.
        ready = harness.wait_for_edge_selection_ready(EDGE_TITLE)
        assert ready, (
            f"Edge fixture did not publish selection-ready marker "
            f"{harness.EDGE_READY_SUFFIX!r} on document title "
            f"{EDGE_TITLE!r} within timeout; the renderer may have "
            "stalled or first-run UI may be covering the page"
        )

        # Focus the Edge window after readiness, then drive the
        # capture. If Ctrl+C raced the renderer's focus event (cold-
        # start window where the omnibox momentarily holds focus
        # before the page content does), re-focus and retry. The
        # fixture's 50 ms JS interval keeps the selection range live
        # across the focus juggling, so each retry only needs to win
        # the focus event before the clipboard read.
        captured = ""
        clipboard_after = ""
        last_focused = False
        for attempt in range(5):
            last_focused = harness.activate_window_by_title_fragment(
                harness.edge_window_title(EDGE_TITLE),
                attempts=60,
            )
            if not last_focused:
                continue
            if attempt > 0:
                # On retry: Ctrl+F6 cycles Edge's focus into the web
                # content area, which is where Ctrl+C must land for the
                # selection to be copied. The fixture's 50 ms JS
                # interval re-asserts the selection range immediately
                # after, so this is a deterministic recovery from a
                # stuck-on-omnibox cold start rather than a sleep.
                harness.send_keys_to_foreground("^{F6}")
            captured, clipboard_after = harness.capture_with_sentinel_clipboard(
                sentinel=EDGE_SENTINEL,
            )
            if captured == EDGE_TEXT:
                break
        assert last_focused, (
            f"Edge window titled {EDGE_TITLE!r} did not accept focus; "
            "Edge may have shown a sign-in / first-run prompt over the page"
        )

        evidence = harness.SmokeEvidence(
            smoke_id="edge_webpage_selected_text_happy_path",
            surface="Edge webpage (local HTML)",
            app_path=str(edge_exe),
            app_version=app_version,
            fixture_path=str(fixture_html),
            expected_text=EDGE_TEXT,
            captured_text=captured,
            matched_expected=(captured == EDGE_TEXT),
            previous_clipboard_sentinel=EDGE_SENTINEL,
            clipboard_after_capture=clipboard_after,
            clipboard_restored=(clipboard_after == EDGE_SENTINEL),
            duration_s=time.monotonic() - started,
            extra={
                "selection_method": (
                    "window.getSelection() + DOM range on load, "
                    "re-applied by 50 ms interval"
                ),
                "selection_ready_signal": "document.title suffix poll",
                "focus_method": "AppActivate + focus-retry capture loop",
                "user_data_dir": str(user_data_dir),
            },
        )
        evidence.write(evidence_dir)

        assert captured == EDGE_TEXT, (
            f"Edge webpage capture mismatch.\n"
            f"  expected: {EDGE_TEXT!r}\n"
            f"  captured: {captured!r}\n"
            f"  app: {edge_exe} ({app_version})"
        )
        assert clipboard_after == EDGE_SENTINEL, (
            "Edge smoke left the clipboard unrestored. "
            f"expected sentinel {EDGE_SENTINEL!r}, "
            f"clipboard now {clipboard_after!r}."
        )
    finally:
        try:
            process.terminate()
        except Exception:
            pass
        harness.force_close_edge_user_data_dir(user_data_dir)
