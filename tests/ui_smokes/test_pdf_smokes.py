"""Maintained PDF selected-text UI smokes (issue #63).

Sibling of ``test_selected_text_smokes.py`` for the v0.2.5 release
gate. Issue #62 covered Notepad and Edge webpages; issue #63 extends
the same harness contract to PDF surfaces:

- Edge built-in PDF viewer with a selectable-text PDF fixture.
- Edge built-in PDF viewer with an image-only PDF fixture (text-layer
  absent), asserting that the empty-capture path preserves the
  clipboard sentinel rather than clobbering it.
- Acrobat / Adobe Reader if installed; otherwise the smoke records
  ``unavailable`` per the shared status contract (not a silent skip,
  not a hard fail).

Protected, scanned, and image-only PDFs are documented as unsupported
until OCR work lands — see ``docs/SELECTED_TEXT_RELIABILITY.md``.

PDF fixtures are synthesised in-test via ``pypdf`` so the repo does
not ship checked-in PDF binaries (matches the #62 HTML-template
strategy in ``_harness.write_edge_fixture``).
"""

from __future__ import annotations

import time
from pathlib import Path

import pytest

from . import _harness as harness

pytestmark = pytest.mark.ui_smoke


# PDF fixture content. Each entry is one PDF text line; viewers
# typically join selected lines with the platform newline. We assert
# against the concatenated body after normalising line endings so the
# smoke does not depend on whether Edge emits ``\r\n`` and Acrobat
# emits ``\n`` (they sometimes disagree). Lines are deliberately short
# enough (<= ~44 ASCII chars) to fit inside a Helvetica 14pt run on a
# US-Letter page with a 72pt left margin, so Ctrl+A in the viewer
# selects every line without wrapping-truncation.
PDF_FIXTURE_LINES: list[str] = [
    "PipPal issue 63 PDF selected-text smoke.",
    "capture_selection must copy this PDF",
    "and restore the previous clipboard.",
]
PDF_EXPECTED_BODY: str = "\n".join(PDF_FIXTURE_LINES)


def _normalise_pdf_capture(text: str) -> str:
    """Normalise line endings emitted by Edge/Acrobat PDF selection.

    Different PDF viewers join multi-line selections differently:
    Edge tends to emit ``\\r\\n`` between lines, Acrobat emits ``\\n``
    or ``\\r``, and some builds inject extra trailing whitespace. We
    normalise to ``\\n`` and strip trailing whitespace per line so
    the smoke asserts text content, not viewer-specific line-ending
    formatting.
    """

    return "\n".join(
        segment.rstrip()
        for segment in text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    ).strip()

EDGE_PDF_SENTINEL_HAPPY = "ISSUE63_EDGE_PDF_HAPPY_PREVIOUS_CLIPBOARD"
EDGE_PDF_SENTINEL_IMAGE_ONLY = "ISSUE63_EDGE_PDF_IMAGE_ONLY_PREVIOUS_CLIPBOARD"
ACROBAT_PDF_SENTINEL_HAPPY = "ISSUE63_ACROBAT_PDF_HAPPY_PREVIOUS_CLIPBOARD"


def _drive_pdf_selection_capture(
    *,
    title_fragment: str,
    sentinel: str,
    expected_text: str,
    process_names: tuple[str, ...],
    select_settle_s: float = 1.2,
    attempts: int = 5,
    match: str = "exact",
    click_into_page: bool = False,
) -> tuple[str, str, bool]:
    """Focus a PDF viewer window, select-all, capture, and report results.

    Returns ``(captured_text, clipboard_after_capture, focused)``. The
    capture is retried up to ``attempts`` times because both Edge's
    PDF viewer and Acrobat sometimes deliver ``Ctrl+A`` to chrome on a
    cold-start focus race; the fixture's selection state is otherwise
    deterministic. This mirrors the Edge HTML smoke's focus-retry
    loop in ``test_edge_webpage_selected_text_happy_path``.
    """

    captured = ""
    clipboard_after = ""
    focused = False
    for attempt in range(attempts):
        # Use the exact-substring activator scoped to the viewer's
        # process name(s). ``WScript.Shell.AppActivate`` is too fuzzy
        # for PDF smokes — on a gate machine with many similarly-
        # titled windows (Serena, multiple editors) it can latch onto
        # the wrong window and silently drive Ctrl+A there.
        focused = harness.activate_window_by_exact_title_substring(
            title_fragment,
            process_names=process_names,
            attempts=30,
        )
        if not focused:
            continue
        # On retry cycle, click into the page area to nudge focus
        # from the viewer's toolbar into the document iframe. This is
        # only needed when the cold-start focus race put the toolbar
        # at the top of the focus chain; the first attempt usually
        # has the document area already focused.
        if click_into_page and attempt > 0:
            harness.click_into_window_center(title_fragment)
            time.sleep(0.3)
        # PDF viewers need a non-trivial settle after focus before
        # Ctrl+A reliably hits the document text layer — the viewer
        # is still wiring up the selection model on first focus.
        time.sleep(select_settle_s)
        # Use the ``keyboard`` Python lib (HID-level injection) for
        # the Ctrl+A / Ctrl+C key combo in PDF surfaces. Edge's
        # built-in PDF viewer is a Chromium PDF.js iframe and does
        # not pick up ``^a`` from ``System.Windows.Forms.SendKeys``
        # even when the document area has the foreground — only HID
        # injection reaches the iframe the way a physical keypress
        # does. ``capture_with_sentinel_clipboard`` already uses the
        # same path for the ``Ctrl+C`` it drives, so the two halves
        # of the select-and-copy sequence are now consistent.
        if not harness.send_hotkey_via_keyboard_lib("ctrl+a"):
            continue
        time.sleep(0.5)  # let the viewer paint the selection
        captured, clipboard_after = harness.capture_with_sentinel_clipboard(
            sentinel=sentinel,
        )
        if match == "normalised":
            matched = _normalise_pdf_capture(captured) == _normalise_pdf_capture(
                expected_text
            )
        else:
            matched = captured == expected_text
        if matched:
            break
    return captured, clipboard_after, focused


# ---------------------------------------------------------------------------
# Edge PDF viewer smokes.
# ---------------------------------------------------------------------------


def test_edge_pdf_selected_text_happy_path(
    edge_exe: Path,
    evidence_dir: Path,
    tmp_path_factory: pytest.TempPathFactory,
) -> None:
    fixture_dir = tmp_path_factory.mktemp("pippal_issue63_edge_pdf_happy")
    user_data_dir = fixture_dir / "edge-profile"
    pdf_path = harness.write_selectable_text_pdf(fixture_dir, PDF_FIXTURE_LINES)

    app_version = harness.get_file_product_version(edge_exe)
    process = harness.launch_edge(
        edge_exe,
        pdf_path,
        user_data_dir=user_data_dir,
        inprivate=True,
    )
    started = time.monotonic()
    try:
        # Wait for Edge's PDF viewer to publish its window title. PDF
        # rendering takes longer than HTML because PDF.js streams the
        # document; without this wait Ctrl+A races against a sync
        # infobar that briefly intercepts focus on some machines.
        title_ready = harness.wait_for_edge_pdf_title(pdf_path)
        assert title_ready, (
            f"Edge PDF viewer window for {pdf_path.name} did not appear "
            "in the OS window list within the load timeout; PDF.js may "
            "have failed to render the fixture"
        )

        captured, clipboard_after, focused = _drive_pdf_selection_capture(
            title_fragment=harness.edge_pdf_window_title(pdf_path),
            sentinel=EDGE_PDF_SENTINEL_HAPPY,
            expected_text=PDF_EXPECTED_BODY,
            process_names=("msedge",),
            match="normalised",
            click_into_page=True,
        )
        normalised_captured = _normalise_pdf_capture(captured)
        normalised_expected = _normalise_pdf_capture(PDF_EXPECTED_BODY)

        evidence = harness.SmokeEvidence(
            smoke_id="edge_pdf_selected_text_happy_path",
            surface="Edge built-in PDF viewer (selectable text)",
            app_path=str(edge_exe),
            app_version=app_version,
            fixture_path=str(pdf_path),
            expected_text=PDF_EXPECTED_BODY,
            captured_text=captured,
            matched_expected=(normalised_captured == normalised_expected),
            previous_clipboard_sentinel=EDGE_PDF_SENTINEL_HAPPY,
            clipboard_after_capture=clipboard_after,
            clipboard_restored=(clipboard_after == EDGE_PDF_SENTINEL_HAPPY),
            duration_s=time.monotonic() - started,
            extra={
                "fixture_strategy": "pypdf BT/Tj Helvetica 3-line content stream",
                "selection_method": "SendKeys ^a in PDF viewer page area",
                "focus_method": "AppActivate + ^{F6} retry loop",
                "edge_flags": "--inprivate --disable-sync (suppresses Edge sync infobar)",
                "match_strategy": "normalised line endings + trimmed lines",
                "user_data_dir": str(user_data_dir),
            },
        )
        evidence.write(evidence_dir)

        assert focused, (
            f"Edge PDF viewer window for {pdf_path.name} did not accept "
            "focus; a first-run prompt may have stolen the foreground"
        )
        assert normalised_captured == normalised_expected, (
            f"Edge PDF capture mismatch.\n"
            f"  expected (normalised): {normalised_expected!r}\n"
            f"  captured (normalised): {normalised_captured!r}\n"
            f"  raw captured:          {captured!r}\n"
            f"  app: {edge_exe} ({app_version})"
        )
        assert clipboard_after == EDGE_PDF_SENTINEL_HAPPY, (
            "Edge PDF smoke left the clipboard unrestored. "
            f"expected sentinel {EDGE_PDF_SENTINEL_HAPPY!r}, "
            f"clipboard now {clipboard_after!r}."
        )
    finally:
        try:
            process.terminate()
        except Exception:
            pass
        harness.force_close_edge_user_data_dir(user_data_dir)


def test_edge_pdf_image_only_records_unsupported(
    edge_exe: Path,
    evidence_dir: Path,
    tmp_path_factory: pytest.TempPathFactory,
) -> None:
    """Image-only / scanned PDFs are unsupported until OCR lands.

    A PDF whose page has no text content stream cannot expose
    selectable text to ``Ctrl+A`` / ``Ctrl+C`` regardless of viewer.
    The smoke asserts the *failure mode* is clean: ``capture_selection``
    returns an empty string and the previous clipboard is preserved.
    If a future viewer change started returning OCR-derived text from
    an image-only PDF this smoke would catch the behavioural shift, at
    which point the reliability matrix and this contract need to be
    revisited together rather than silently broadening claims.
    """

    fixture_dir = tmp_path_factory.mktemp("pippal_issue63_edge_pdf_image_only")
    user_data_dir = fixture_dir / "edge-profile"
    pdf_path = harness.write_image_only_pdf(fixture_dir)

    app_version = harness.get_file_product_version(edge_exe)
    process = harness.launch_edge(
        edge_exe,
        pdf_path,
        user_data_dir=user_data_dir,
        inprivate=True,
    )
    started = time.monotonic()
    try:
        title_ready = harness.wait_for_edge_pdf_title(pdf_path)
        assert title_ready, (
            f"Edge PDF viewer window for image-only fixture {pdf_path.name} "
            "did not appear in the OS window list within the load timeout"
        )
        captured, clipboard_after, focused = _drive_pdf_selection_capture(
            title_fragment=harness.edge_pdf_window_title(pdf_path),
            sentinel=EDGE_PDF_SENTINEL_IMAGE_ONLY,
            process_names=("msedge",),
            # No text layer => no expected text. We pass the empty
            # string so the retry loop does not spin looking for a
            # match that cannot exist; one attempt is enough to
            # establish the empty-capture contract.
            expected_text="",
            attempts=1,
            click_into_page=True,
        )

        evidence = harness.SmokeEvidence(
            smoke_id="edge_pdf_image_only_records_unsupported",
            surface="Edge built-in PDF viewer (no text layer)",
            app_path=str(edge_exe),
            app_version=app_version,
            fixture_path=str(pdf_path),
            expected_text="",
            captured_text=captured,
            matched_expected=(captured == ""),
            previous_clipboard_sentinel=EDGE_PDF_SENTINEL_IMAGE_ONLY,
            clipboard_after_capture=clipboard_after,
            clipboard_restored=(clipboard_after == EDGE_PDF_SENTINEL_IMAGE_ONLY),
            duration_s=time.monotonic() - started,
            extra={
                "fixture_strategy": "pypdf blank page (no /Contents text stream)",
                "rationale": (
                    "Image-only / scanned PDFs have no text layer; "
                    "capture_selection must return empty and preserve "
                    "the user's clipboard. Unsupported until OCR work "
                    "lands; tracked separately from this gate."
                ),
            },
        )
        evidence.write(evidence_dir)

        assert focused, (
            f"Edge PDF viewer window for {pdf_path.name} did not accept "
            "focus on the image-only fixture"
        )
        assert captured == "", (
            "Edge PDF image-only capture leaked text. capture_selection "
            f"returned {captured!r}; an image-only fixture must produce "
            "an empty capture until OCR work lands."
        )
        assert clipboard_after == EDGE_PDF_SENTINEL_IMAGE_ONLY, (
            "Edge PDF image-only smoke clobbered the clipboard. "
            f"expected sentinel {EDGE_PDF_SENTINEL_IMAGE_ONLY!r}, "
            f"clipboard now {clipboard_after!r}. "
            "Core must restore the previous clipboard even when the PDF "
            "has no text layer."
        )
    finally:
        try:
            process.terminate()
        except Exception:
            pass
        harness.force_close_edge_user_data_dir(user_data_dir)


# ---------------------------------------------------------------------------
# Acrobat / Adobe Reader smoke (optional, surfaces `unavailable` cleanly).
# ---------------------------------------------------------------------------


def test_acrobat_pdf_selected_text_or_blocked(
    acrobat_exe: Path | None,
    evidence_dir: Path,
    tmp_path_factory: pytest.TempPathFactory,
) -> None:
    """Acrobat happy path when installed, structured ``unavailable`` otherwise.

    Per the release-gate status contract in ``docs/RELEASE_CHECKLIST.md``,
    Acrobat absence is not a fail and not a silent skip: we write an
    evidence file naming the searched paths and then ``pytest.skip``
    with a machine-readable reason. The runner's ``-AllowUnavailable``
    flag promotes the resulting all-skipped Acrobat result to
    ``unavailable``; without that flag it is ``blocked`` and the
    release reviewer must explicitly waive per the documented policy.
    """

    if acrobat_exe is None:
        searched = [str(p) for p in harness.ACROBAT_CANDIDATES]
        evidence_path = evidence_dir / "acrobat_pdf_selected_text_unavailable.json"
        evidence = harness.SmokeEvidence(
            smoke_id="acrobat_pdf_selected_text_unavailable",
            surface="Acrobat / Adobe Reader (not installed)",
            app_path="",
            app_version="not installed",
            fixture_path="",
            expected_text=PDF_EXPECTED_BODY,
            captured_text="",
            matched_expected=False,
            previous_clipboard_sentinel=ACROBAT_PDF_SENTINEL_HAPPY,
            clipboard_after_capture="",
            clipboard_restored=False,
            duration_s=0.0,
            extra={
                "status": "unavailable",
                "searched_paths": searched,
                "rationale": (
                    "Neither Acrobat.exe nor AcroRd32.exe found in the "
                    "candidate paths on this gate machine. Recorded as "
                    "unavailable per the release-gate status contract."
                ),
            },
        )
        evidence.write(evidence_dir)
        pytest.skip(
            f"Acrobat / Adobe Reader not installed (searched {searched}); "
            f"evidence recorded at {evidence_path}"
        )

    fixture_dir = tmp_path_factory.mktemp("pippal_issue63_acrobat_pdf")
    pdf_path = harness.write_selectable_text_pdf(fixture_dir, PDF_FIXTURE_LINES)

    app_version = harness.get_file_product_version(acrobat_exe)
    process = harness.launch_acrobat(acrobat_exe, pdf_path)
    started = time.monotonic()
    try:
        # Wait for Acrobat to publish a titled document window. If the
        # box has a stuck sign-in / EULA modal Acrobat keeps the
        # document window untitled and AppActivate silently fails;
        # we record that as ``blocked`` (machine-readable evidence
        # plus pytest.skip with the searched paths) rather than a
        # hard fail, per the release-gate status contract. The
        # release reviewer can then either repair the Acrobat
        # install or waive with ``-AllowUnavailable``.
        title_ready = harness.wait_for_acrobat_title(pdf_path)
        if not title_ready:
            evidence = harness.SmokeEvidence(
                smoke_id="acrobat_pdf_selected_text_blocked_no_window_title",
                surface="Acrobat / Adobe Reader (no titled document window)",
                app_path=str(acrobat_exe),
                app_version=app_version,
                fixture_path=str(pdf_path),
                expected_text=PDF_EXPECTED_BODY,
                captured_text="",
                matched_expected=False,
                previous_clipboard_sentinel=ACROBAT_PDF_SENTINEL_HAPPY,
                clipboard_after_capture="",
                clipboard_restored=False,
                duration_s=time.monotonic() - started,
                extra={
                    "status": "blocked",
                    "failure_symptom": (
                        "Acrobat process is running but no document "
                        "window with a title containing the PDF stem "
                        "appeared within the load timeout. Likely a "
                        "stuck sign-in / EULA / update prompt is "
                        "holding the foreground."
                    ),
                    "candidate_fix": (
                        "Manually launch Acrobat once on the gate "
                        "machine, dismiss any sign-in / update prompt, "
                        "then re-run the gate. If the prompt cannot be "
                        "dismissed, mark this smoke as -AllowUnavailable "
                        "with a follow-up issue per RELEASE_CHECKLIST.md."
                    ),
                },
            )
            evidence.write(evidence_dir)
            pytest.skip(
                f"Acrobat opened but never published a titled document "
                f"window for {pdf_path.name}; recorded as blocked at "
                f"{evidence_dir / evidence.smoke_id}.json"
            )

        # Acrobat cold-start can show a "Tools" pane / sign-in pane that
        # holds focus. The retry loop in _drive_pdf_selection_capture
        # uses Ctrl+F6 to cycle into the document pane, which is the
        # same shortcut Acrobat documents for keyboard navigation.
        captured, clipboard_after, focused = _drive_pdf_selection_capture(
            title_fragment=harness.acrobat_window_title(pdf_path),
            sentinel=ACROBAT_PDF_SENTINEL_HAPPY,
            expected_text=PDF_EXPECTED_BODY,
            process_names=("Acrobat", "AcroRd32"),
            select_settle_s=1.5,
            attempts=6,
            match="normalised",
        )
        normalised_captured = _normalise_pdf_capture(captured)
        normalised_expected = _normalise_pdf_capture(PDF_EXPECTED_BODY)

        evidence = harness.SmokeEvidence(
            smoke_id="acrobat_pdf_selected_text_happy_path",
            surface="Acrobat / Adobe Reader (selectable text)",
            app_path=str(acrobat_exe),
            app_version=app_version,
            fixture_path=str(pdf_path),
            expected_text=PDF_EXPECTED_BODY,
            captured_text=captured,
            matched_expected=(normalised_captured == normalised_expected),
            previous_clipboard_sentinel=ACROBAT_PDF_SENTINEL_HAPPY,
            clipboard_after_capture=clipboard_after,
            clipboard_restored=(clipboard_after == ACROBAT_PDF_SENTINEL_HAPPY),
            duration_s=time.monotonic() - started,
            extra={
                "fixture_strategy": "pypdf BT/Tj Helvetica 3-line content stream",
                "selection_method": "SendKeys ^a in Acrobat document pane",
                "focus_method": "AppActivate + ^{F6} retry loop",
                "match_strategy": "normalised line endings + trimmed lines",
            },
        )
        evidence.write(evidence_dir)

        assert focused, (
            f"Acrobat window for {pdf_path.name} did not accept focus; "
            "an Acrobat sign-in / tools pane may be in the foreground"
        )
        assert normalised_captured == normalised_expected, (
            f"Acrobat PDF capture mismatch.\n"
            f"  expected (normalised): {normalised_expected!r}\n"
            f"  captured (normalised): {normalised_captured!r}\n"
            f"  raw captured:          {captured!r}\n"
            f"  app: {acrobat_exe} ({app_version})"
        )
        assert clipboard_after == ACROBAT_PDF_SENTINEL_HAPPY, (
            "Acrobat smoke left the clipboard unrestored. "
            f"expected sentinel {ACROBAT_PDF_SENTINEL_HAPPY!r}, "
            f"clipboard now {clipboard_after!r}."
        )
    finally:
        try:
            process.terminate()
        except Exception:
            pass
        harness.force_close_acrobat_for(pdf_path)
