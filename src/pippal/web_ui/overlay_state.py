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

        self._chunk_text: str = ""
        self._words: list[dict[str, float]] = []
        self._chunk_start: float = 0.0
        self._chunk_duration: float = 0.0
        self._chunk_idx: int = 0
        self._chunk_total: int = 1

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

    def set_paused(self, paused: bool) -> None:
        with self._lock:
            if paused and not self.paused:
                self._paused_elapsed = max(0.0, time.time() - self._chunk_start)
                self.paused = True
            elif (not paused) and self.paused:
                self._chunk_start = time.time() - self._paused_elapsed
                self.paused = False

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

    def start_chunk(
        self,
        text: str,
        duration: float,
        idx: int = 0,
        total: int = 1,
        offset_s: float = 0.0,
    ) -> None:
        words = _word_timings(text, duration)
        with self._lock:
            # A fresh chunk means a fresh reading — kill any pending
            # auto-hide (Tk does this via _cancel_hide in _set_state).
            self._cancel_hide_locked()
            self._chunk_text = text
            self._words = words
            self._chunk_idx = idx
            self._chunk_total = total
            if words:
                self._chunk_duration = duration
                self._chunk_start = time.time() + offset_s
                self.paused = False

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
            if self.paused:
                elapsed = self._paused_elapsed
            else:
                elapsed = time.time() - self._chunk_start
            return {
                "overlay_state": self.state,
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
