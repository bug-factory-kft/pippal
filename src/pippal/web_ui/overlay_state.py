"""Headless overlay-state mirror for the web reader panel.

The backend (``pippal.engine`` / ``pippal.playback``) talks to whatever
object satisfies the overlay protocol — ``set_state`` / ``start_chunk``
/ ``show_message`` / ``set_paused`` / ``set_action_label``.

``WebOverlay`` implements exactly that protocol with plain Python
state. It computes per-word karaoke timings with the pure helpers
(``text_utils.word_timing_weight`` / ``iter_word_spans``), so the
highlight cadence is deterministic. The browser polls :meth:`snapshot`
and does the painting.

**Auto-hide.** When the engine flips the overlay to ``done`` it should
stay visible for ``max(OVERLAY_HIDE_MIN_MS, auto_hide_ms)`` and a
one-shot message for ``OVERLAY_MESSAGE_MS``. ``_NullRoot.after`` in the
web app runs immediate callbacks inline, so a timed hide there would
fire instantly. ``WebOverlay`` therefore owns its OWN
``threading.Timer`` so the panel stays visible for the configured
``auto_hide_ms`` and then genuinely hides. Any new ``set_state`` /
``start_chunk`` / explicit ``hide`` cancels a pending timer first.
"""

from __future__ import annotations

import threading
import time
from typing import Any

from ..config import DEFAULT_CONFIG
from ..text_utils import iter_word_spans, word_timing_weight
from ..timing import OVERLAY_HIDE_MIN_MS, OVERLAY_MESSAGE_MS


class WebOverlay:
    """Thread-safe overlay state the engine drives and the web UI polls.
    Implements the overlay protocol the engine/playback loop calls."""

    def __init__(self, config: dict[str, Any]) -> None:
        self.config = config
        self._lock = threading.Lock()
        self.state: str = "idle"          # idle | thinking | reading | done
        self.message: str = ""
        self.action_label: str | None = None
        self.paused: bool = False
        self._paused_elapsed: float = 0.0
        # True between ``set_paused(False)`` and the playback loop's
        # follow-up ``start_chunk`` that re-arms the resume clock. While
        # set, ``snapshot`` keeps reporting the frozen paused elapsed so
        # the karaoke highlight does not flicker to word 0 in the gap.
        self._resuming: bool = False
        # Clock the karaoke timer reads. Injectable so tests can drive
        # ``elapsed`` deterministically; defaults to wall time.
        self._clock = time.time

        self._chunk_text: str = ""
        self._words: list[dict[str, float]] = []
        self._chunk_start: float = 0.0
        self._chunk_duration: float = 0.0
        self._chunk_idx: int = 0
        self._chunk_total: int = 1

        # Authoritative "a real (cache-miss) synth is running RIGHT NOW" flag.
        # This is the EVENT-DRIVEN loader signal: it flips True the instant a
        # genuine synth begins (``begin_synth``) and flips False the instant
        # audio is ready and published (``start_chunk``). The web UI binds the
        # loading indicator directly to this flag, so the loader can never
        # outlive the actual synth — it is NOT inferred from the coarse
        # ``thinking`` state nor gated on a poll heuristic. For a cache-HIT
        # chunk ``begin_synth`` is never called, so the loader never shows.
        self._is_synthesizing: bool = False

        # Auto-hide timer (the web analogue of the Tk overlay's
        # ``root.after(delay, self._hide)``). Guarded by ``_lock``.
        self._hide_timer: threading.Timer | None = None
        self._hide_generation: int = 0

    # ----- engine-facing protocol (all no-ops when overlay disabled) ---

    def _enabled(self) -> bool:
        return bool(self.config.get("show_overlay", True))

    def set_action_label(self, label: str | None) -> None:
        with self._lock:
            self.action_label = label

    def begin_synth(self) -> None:
        """Announce that a real (cache-miss) synth has started.

        This is the authoritative "loading" EVENT: the web UI shows the loader
        only while this flag is set. The matching clear happens in
        ``start_chunk`` (audio ready) — never on a timer. A no-op when the
        overlay is disabled.
        """
        if not self._enabled():
            return
        with self._lock:
            self._is_synthesizing = True

    def end_synth(self) -> None:
        """Clear the synth flag without publishing a chunk.

        Used when a synth is abandoned/superseded (navigate-during-synth) so
        the loader does not linger for a target the user already skipped past.
        """
        with self._lock:
            self._is_synthesizing = False

    def set_paused(self, paused: bool) -> None:
        with self._lock:
            if paused and not self.paused:
                self._paused_elapsed = max(0.0, self._clock() - self._chunk_start)
                self.paused = True
            elif (not paused) and self.paused:
                # SINGLE SOURCE OF TRUTH for resume-elapsed: do NOT rebase
                # ``_chunk_start`` here. The playback loop re-arms the
                # karaoke clock via ``start_chunk`` with the audio tail's
                # elapsed; rebasing here too caused a double reset race
                # that collapsed the snapshot ``elapsed`` to ~0 (the
                # highlight jumped back to word 0 on resume). Keep the
                # frozen ``_paused_elapsed`` visible until ``start_chunk``
                # establishes the authoritative resume clock.
                self.paused = False
                self._resuming = True

    def set_state(self, state: str) -> None:
        if not self._enabled():
            return
        with self._lock:
            self._cancel_hide_locked()
            self.state = state
            self.message = ""
            if state != "reading":
                self._words = []
                self._chunk_text = ""
            if state == "done":
                # Completion edge — drop any loader flag left over from an
                # early loading-first ``begin_synth`` (event-driven hide,
                # no timer; spec H5).
                self._is_synthesizing = False
                # Mirror Tk Overlay._set_state("done"): schedule a real
                # auto-hide after max(OVERLAY_HIDE_MIN_MS, auto_hide_ms).
                delay_ms = max(
                    OVERLAY_HIDE_MIN_MS,
                    int(self.config.get(
                        "auto_hide_ms", DEFAULT_CONFIG["auto_hide_ms"])),
                )
                self._arm_hide_locked(delay_ms)

    def show_message(self, msg: str) -> None:
        if not self._enabled():
            return
        with self._lock:
            self._cancel_hide_locked()
            self.message = msg
            self.state = "done"
            self._words = []
            self._chunk_text = ""
            # A one-shot message is a completion edge (e.g. "No text
            # selected" after a failed capture, or a success/error banner):
            # clear the loader flag so an early ``begin_synth`` from the
            # loading-first chokepoint does not linger over the banner.
            self._is_synthesizing = False
            # Mirror Tk Overlay._show_message: one-shot messages self
            # dismiss after OVERLAY_MESSAGE_MS regardless of auto_hide_ms.
            self._arm_hide_locked(OVERLAY_MESSAGE_MS)

    def hide(self) -> None:
        with self._lock:
            self._cancel_hide_locked()
            self.state = "idle"
            self.message = ""
            self._words = []
            self._chunk_text = ""
            self.action_label = None
            self._is_synthesizing = False

    def start_chunk(
        self,
        text: str,
        duration: float,
        idx: int = 0,
        total: int = 1,
        offset_s: float = 0.0,
        resume_elapsed_s: float | None = None,
    ) -> None:
        """Arm the karaoke clock for a chunk.

        ``offset_s`` is the latency compensation (karaoke_offset_s): the
        clock starts that far in the future so the highlight does not run
        ahead of audio startup.

        ``resume_elapsed_s`` is the SINGLE SOURCE OF TRUTH for a resume.
        When set, the chunk is treated as already ``resume_elapsed_s``
        seconds in (the audio tail resumed there), so the snapshot
        ``elapsed`` lands at ``resume_elapsed_s`` rather than 0. This is
        the only place the resume clock is rebased — ``set_paused(False)``
        deliberately does not, to avoid the double-reset race.
        """
        words = _word_timings(text, duration)
        with self._lock:
            # A fresh chunk means a fresh reading — kill any pending
            # auto-hide (Tk does this via _cancel_hide in _set_state).
            self._cancel_hide_locked()
            # Audio for this chunk is ready and being published NOW — this is
            # the authoritative "synth done / ready" edge. Clear the loader
            # flag here (event-driven), so the loader hides exactly when the
            # chunk text/words become available, with no poll lag.
            self._is_synthesizing = False
            self._chunk_text = text
            self._words = words
            self._chunk_idx = idx
            self._chunk_total = total
            if words:
                self._chunk_duration = duration
                base = resume_elapsed_s if resume_elapsed_s is not None else 0.0
                # elapsed = clock() - _chunk_start, so to land at
                # ``base`` now we set _chunk_start = clock() - base. The
                # latency ``offset_s`` still pushes the clock forward.
                self._chunk_start = self._clock() - base + offset_s
                self.paused = False
            self._resuming = False

    # ----- auto-hide scheduling (lock held by caller) -----------------

    def _cancel_hide_locked(self) -> None:
        """Cancel a pending auto-hide. Mirrors Tk Overlay._cancel_hide.

        Bumping the generation makes a timer that already fired (and is
        waiting on ``_lock``) a no-op when it finally runs.
        """
        self._hide_generation += 1
        if self._hide_timer is not None:
            try:
                self._hide_timer.cancel()
            except Exception:
                pass
            self._hide_timer = None

    def _arm_hide_locked(self, delay_ms: int) -> None:
        """Schedule a real hide after ``delay_ms``. The web analogue of
        ``self.root.after(delay, self._hide)`` in the Tk overlay."""
        gen = self._hide_generation
        timer = threading.Timer(
            max(0, delay_ms) / 1000.0, self._on_hide_timeout, args=(gen,)
        )
        timer.daemon = True
        self._hide_timer = timer
        timer.start()

    def _on_hide_timeout(self, generation: int) -> None:
        with self._lock:
            # A newer state transition cancelled/superseded this timer.
            if generation != self._hide_generation:
                return
            self._hide_timer = None
            self.state = "idle"
            self.message = ""
            self._words = []
            self._chunk_text = ""
            self.action_label = None

    # ----- web-facing snapshot ----------------------------------------

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            if self.paused or self._resuming:
                # Frozen while paused, and held frozen across the brief
                # resume gap until ``start_chunk`` re-arms the clock — so
                # the karaoke highlight never flickers back to word 0.
                elapsed = self._paused_elapsed
            else:
                elapsed = self._clock() - self._chunk_start
            return {
                "overlay_state": self.state,
                "is_synthesizing": self._is_synthesizing,
                "overlay_message": self.message,
                "action_label": self.action_label,
                "is_paused": self.paused,
                "chunk_text": self._chunk_text,
                "chunk_duration": self._chunk_duration,
                "chunk_idx": self._chunk_idx,
                "chunk_total": self._chunk_total,
                "elapsed": max(0.0, elapsed),
                "words": list(self._words),
                "brand_name": self.config.get("brand_name", "PipPal"),
            }


def _word_timings(text: str, duration: float) -> list[dict[str, float]]:
    """Per-word (word, ts, te) using the syllable-weighted timing in
    ``text_utils``, minus the pixel layout the browser reflows on its
    own."""
    words = list(iter_word_spans(text))
    if not words or duration <= 0:
        return []
    weights = [word_timing_weight(m.group()) for m in words]
    total_weight = sum(weights) or 1.0
    head = min(0.12, duration * 0.05)
    tail = min(0.12, duration * 0.05)
    usable = max(0.1, duration - head - tail)
    out: list[dict[str, float]] = []
    accum = 0.0
    for m, weight in zip(words, weights):
        ts = head + (accum / total_weight) * usable
        accum += weight
        te = head + (accum / total_weight) * usable
        out.append({"word": m.group(), "ts": ts, "te": te})
    return out
