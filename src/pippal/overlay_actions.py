"""Overlay action chokepoint — show the loading indicator FIRST.

Every overlay-bearing action (normal read / queue-idle / read-text /
replay-text in core, plus AI actions and WAV export in Pro) must put the
overlay into a VISIBLE loading state SYNCHRONOUSLY, before any blocking
text-prep work (``clipboard_capture.capture_for_action``, document
extraction, first-chunk synth, save dialog). Otherwise the window cannot
pop until that work finishes — the "overlay appears with a delay" bug.

This module owns the ONE common chokepoint helper so no entry point has to
copy-paste the ``set_state`` / ``begin_synth`` lines (DRY — spec S1). Each
entry point calls :func:`begin_action_overlay` as its FIRST statement.

State choice (spec S2 / H1): we reuse the EXISTING ``loading`` state rather
than inventing a new one. ``loading`` is a DISTINCT state from the
pre-capture ``thinking`` state, and the overlay-window controller
(``OverlayWindowController._should_be_visible``) already treats ``loading``
as visible and shows it via the no-activate path — so the window pops with
the in-body loader WITHOUT stealing foreground during the synthetic-Ctrl+C
selection capture (#265 stays preserved precisely because ``thinking`` and
``loading`` remain different states). ``begin_synth`` flips the
event-driven ``_is_synthesizing`` flag that drives the in-body loader; it is
cleared on the audio-ready edge by ``start_chunk`` (spec H5 — no timer-based
hide). The call is cheap and non-blocking (spec H4): two locked field
writes, no I/O.

The same helper is importable from Pro entry points so they share the exact
chokepoint::

    from pippal.overlay_actions import begin_action_overlay
    begin_action_overlay(engine)
"""

from __future__ import annotations

from typing import Any


def begin_action_overlay(engine: Any) -> None:
    """Put the overlay into the VISIBLE loading state, synchronously, FIRST.

    Call this as the FIRST statement of any overlay-bearing action handler,
    BEFORE capture / extraction / synth / save-dialog. After it returns the
    overlay has already reached a ``_should_be_visible() == True`` loading
    state, so the window can pop immediately (no-activate) with the in-body
    loader while the slow text-prep runs on the worker thread.

    A no-op when the engine has no overlay attached (core builds without a
    web overlay, or ``show_overlay`` disabled — the overlay protocol methods
    are themselves no-ops in that case).
    """
    overlay = engine._overlay()
    if overlay is None:
        return
    # Order matters: flip to the visible ``loading`` state, then arm the
    # event-driven loader flag. Both are cheap, non-blocking field writes.
    overlay.set_state("loading")
    begin_synth = getattr(overlay, "begin_synth", None)
    if callable(begin_synth):
        begin_synth()
