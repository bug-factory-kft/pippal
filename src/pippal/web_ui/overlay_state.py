"""Headless overlay-state mirror for the web reader panel.

The Tk :class:`pippal.ui.overlay.Overlay` is bound to tkinter (Canvas,
``tk.after`` animation loop). The web overlay can't use it, but the
backend (``pippal.engine`` / ``pippal.playback``) talks to whatever
object satisfies the overlay protocol — ``set_state`` / ``start_chunk``
/ ``show_message`` / ``set_paused`` / ``set_action_label``.

``WebOverlay`` implements exactly that protocol with plain Python
state. It computes per-word karaoke timings with the SAME pure helpers
(``text_utils.word_timing_weight`` / ``iter_word_spans``) the Tk
``overlay_paint.compute_word_layout`` uses, so the highlight cadence
matches. The browser polls :meth:`snapshot` and does the painting.

This adds an alternative overlay sink; it does not change any backend
behaviour.
"""

from __future__ import annotations

import threading
import time
from typing import Any

from ..text_utils import iter_word_spans, word_timing_weight


class WebOverlay:
    """Thread-safe, tk-free overlay state the engine drives and the web
    UI polls. Mirrors the public surface of ``pippal.ui.overlay.Overlay``
    that the engine/playback loop actually calls."""

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
            self.state = state
            self.message = ""
            if state != "reading":
                self._words = []
                self._chunk_text = ""

    def show_message(self, msg: str) -> None:
        if not self._enabled():
            return
        with self._lock:
            self.message = msg
            self.state = "done"

    def hide(self) -> None:
        with self._lock:
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
            self._chunk_text = text
            self._words = words
            self._chunk_idx = idx
            self._chunk_total = total
            if words:
                self._chunk_duration = duration
                self._chunk_start = time.time() + offset_s
                self.paused = False

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
    """Per-word (word, ts, te) using the same weighting the Tk overlay
    uses (``overlay_paint.compute_word_layout``), minus the pixel
    layout the browser reflows on its own."""
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
