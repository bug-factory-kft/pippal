"""The frameless reading panel.

A floating, transparent-cornered Toplevel that sits at the bottom of
the screen. Renders the current sentence as static text and animates
only the colour of each word so that the bright/bold "current word"
reads as a karaoke cursor.

This file owns the **lifecycle** of the panel (state transitions,
animation scheduling, click + drag handling). The actual drawing lives
in :mod:`pippal.ui.overlay_paint`."""

from __future__ import annotations

import sys
import time
import tkinter as tk
from collections.abc import Callable
from tkinter import font as tkfont
from typing import Any

from ..config import DEFAULT_CONFIG
from ..timing import (
    OVERLAY_FRAME_MS,
    OVERLAY_HIDE_MIN_MS,
    OVERLAY_MESSAGE_MS,
)
from . import overlay_paint as paint
from .overlay_paint import WordSpan, compute_word_layout

# Re-export so existing imports (`from pippal.ui.overlay import WordSpan`)
# keep working.
__all__ = ["Overlay", "WordSpan"]


class Overlay:
    """Lifecycle controller for the reader panel.

    Holds state (`state`, `paused`, `word_layout`, etc.), schedules
    redraws via `tk.after`, and dispatches clicks. Drawing is delegated
    to :func:`pippal.ui.overlay_paint.paint`."""

    WIDTH: int = 760
    TRANS_COLOR: str = "#010203"

    PADDING_X: int = 32
    PADDING_TOP: int = 18
    PADDING_BOTTOM: int = 22
    HEADER_H: int = 24
    LINE_H: int = 30
    BODY_TOP_GAP: int = 14
    BAR_H: int = 4
    MIN_HEIGHT: int = 88

    # Close-button hit-rect — kept here so paint_header() and _on_click()
    # use a single source of truth.
    _CLOSE_BTN_RECT: tuple[int, int, int, int] = (WIDTH - 38, 8, WIDTH - 12, 34)

    def __init__(
        self,
        root: tk.Misc,
        config: dict[str, Any],
        on_stop: Callable[[], None] | None = None,
        on_prev: Callable[[], None] | None = None,
        on_replay: Callable[[], None] | None = None,
        on_next: Callable[[], None] | None = None,
    ) -> None:
        self.root = root
        self.config = config
        self.on_stop = on_stop
        self.on_prev = on_prev
        self.on_replay = on_replay
        self.on_next = on_next
        self._btn_rects: dict[str, tuple[int, int, int, int]] = {}

        self.win = tk.Toplevel(root)
        self.win.overrideredirect(True)
        self.win.attributes("-topmost", True)
        self.win.attributes("-alpha", 0.96)
        self.win.configure(bg=self.TRANS_COLOR)
        try:
            self.win.attributes("-transparentcolor", self.TRANS_COLOR)
        except Exception:
            pass

        self._height: int = self.MIN_HEIGHT
        self.canvas = tk.Canvas(
            self.win, width=self.WIDTH, height=self._height,
            bg=self.TRANS_COLOR, highlightthickness=0, bd=0,
        )
        self.canvas.pack()
        self.canvas.bind("<Button-1>", self._on_click)

        self.font_text = tkfont.Font(family="Segoe UI", size=14)
        self.font_text_bold = tkfont.Font(family="Segoe UI Semibold",
                                          size=14, weight="bold")
        self.font_status = tkfont.Font(family="Segoe UI", size=10)
        self.font_close = tkfont.Font(family="Segoe UI", size=12)

        self.state: str = "idle"   # idle / thinking / reading / done
        self.message: str = ""
        self.phase: int = 0
        self._anim_id: str | None = None
        self._hide_id: str | None = None

        self.word_layout: list[WordSpan] = []
        self.line_count: int = 0
        self.chunk_start_time: float = 0.0
        self.chunk_duration: float = 0.0
        self.chunk_idx: int = 0
        self.chunk_total: int = 1
        self.action_label: str | None = None

        self.paused: bool = False
        self.paused_elapsed: float = 0.0

        self._drag = {"x": 0, "y": 0}
        self.canvas.bind("<ButtonPress-3>", self._drag_start)
        self.canvas.bind("<B3-Motion>", self._drag_move)

        self.win.withdraw()
        self._draw()

    # ------------------------------------------------------------------
    # Thread-safe public API — every entry point hops onto the UI thread.
    # ------------------------------------------------------------------

    def set_action_label(self, label: str | None) -> None:
        self.root.after(0, lambda: setattr(self, "action_label", label))

    def set_paused(self, paused: bool) -> None:
        self.root.after(0, self._set_paused_impl, paused)

    def set_state(self, state: str) -> None:
        self.root.after(0, self._set_state, state)

    def show_message(self, msg: str) -> None:
        self.root.after(0, self._show_message, msg)

    def hide(self) -> None:
        self.root.after(0, self._hide)

    def start_chunk(
        self,
        text: str,
        duration: float,
        idx: int = 0,
        total: int = 1,
        offset_s: float = 0.0,
    ) -> None:
        self.root.after(0, self._start_chunk_impl, text, duration, idx, total, offset_s)

    # ------------------------------------------------------------------
    # UI-thread implementations
    # ------------------------------------------------------------------

    def _set_paused_impl(self, paused: bool) -> None:
        if paused and not self.paused:
            self.paused_elapsed = max(0.0, time.time() - self.chunk_start_time)
            self.paused = True
        elif (not paused) and self.paused:
            self.chunk_start_time = time.time() - self.paused_elapsed
            self.paused = False
        self._draw()

    def _start_chunk_impl(
        self,
        text: str,
        duration: float,
        idx: int = 0,
        total: int = 1,
        offset_s: float = 0.0,
    ) -> None:
        self.chunk_idx = idx
        self.chunk_total = total
        self.word_layout = compute_word_layout(
            text, duration, self.font_text_bold,
            self.WIDTH, self.PADDING_X,
            self.font_text.measure(" "),
        )
        self.line_count = (self.word_layout[-1].y + 1) if self.word_layout else 1
        if self.word_layout:
            self.chunk_duration = duration
            self.chunk_start_time = time.time() + offset_s
            self._set_height(self._compute_height(self.line_count))
        else:
            self._set_height(self.MIN_HEIGHT)

    def _compute_height(self, lines: int) -> int:
        return (
            self.PADDING_TOP + self.HEADER_H + self.BODY_TOP_GAP
            + lines * self.LINE_H + 6
            + self.BAR_H + self.PADDING_BOTTOM
        )

    def _set_height(self, h: int) -> None:
        h = int(h)
        if h == self._height:
            return
        self._height = h
        try:
            self.canvas.config(height=h)
        except Exception:
            pass
        if self.win.winfo_viewable():
            self._show()

    def _set_state(self, state: str) -> None:
        if not self.config.get("show_overlay", True):
            return
        self.state = state
        self.message = ""
        if state != "reading":
            self.word_layout = []
            self.line_count = 0
            self._set_height(self.MIN_HEIGHT)
        if state in ("thinking", "reading"):
            self._cancel_hide()
            self._show()
            self._start_anim()
        elif state == "done":
            self._cancel_hide()
            self._draw()
            delay = max(OVERLAY_HIDE_MIN_MS, int(self.config.get(
                "auto_hide_ms", DEFAULT_CONFIG["auto_hide_ms"])))
            self._hide_id = self.root.after(delay, self._hide)
        else:
            self._hide()

    def _show_message(self, msg: str) -> None:
        if not self.config.get("show_overlay", True):
            return
        self.message = msg
        self.state = "done"
        self._cancel_hide()
        self._show()
        self._draw()
        self._hide_id = self.root.after(OVERLAY_MESSAGE_MS, self._hide)

    def _show(self) -> None:
        sw = self.win.winfo_screenwidth()
        sh = self.win.winfo_screenheight()
        x = (sw - self.WIDTH) // 2
        y = sh - self._height - int(self.config.get(
            "overlay_y_offset", DEFAULT_CONFIG["overlay_y_offset"]))
        self.win.geometry(f"{self.WIDTH}x{self._height}+{x}+{y}")
        try:
            self.win.deiconify()
            self.win.attributes("-topmost", True)
        except Exception:
            pass

    def _hide(self) -> None:
        self._cancel_hide()
        self._stop_anim()
        self.word_layout = []
        self.line_count = 0
        self.action_label = None
        self._set_height(self.MIN_HEIGHT)
        try:
            self.win.withdraw()
        except Exception:
            pass

    def _cancel_hide(self) -> None:
        if self._hide_id:
            try:
                self.root.after_cancel(self._hide_id)
            except Exception:
                pass
            self._hide_id = None

    def _start_anim(self) -> None:
        if self._anim_id is not None:
            return

        def step() -> None:
            self.phase += 1
            self._draw()
            self._anim_id = self.root.after(OVERLAY_FRAME_MS, step)

        step()

    def _stop_anim(self) -> None:
        if self._anim_id is not None:
            try:
                self.root.after_cancel(self._anim_id)
            except Exception:
                pass
            self._anim_id = None

    # ------------------------------------------------------------------
    # Mouse handling
    # ------------------------------------------------------------------

    def _drag_start(self, ev: tk.Event) -> None:
        self._drag["x"] = ev.x_root - self.win.winfo_x()
        self._drag["y"] = ev.y_root - self.win.winfo_y()

    def _drag_move(self, ev: tk.Event) -> None:
        try:
            self.win.geometry(
                f"+{ev.x_root - self._drag['x']}+{ev.y_root - self._drag['y']}",
            )
        except Exception:
            pass

    @staticmethod
    def _safe(handler: Callable[[], None] | None) -> None:
        # Tk callbacks must not raise — an exception here kills the
        # callback dispatcher for the rest of the app.
        if handler is None:
            return
        try:
            handler()
        except Exception as e:
            print(f"[overlay] click handler failed: {e}", file=sys.stderr)

    def _on_click(self, ev: tk.Event) -> None:
        x1, y1, x2, y2 = self._CLOSE_BTN_RECT
        if x1 <= ev.x <= x2 and y1 <= ev.y <= y2:
            self._safe(self.on_stop)
            return
        for tag, (bx1, by1, bx2, by2) in self._btn_rects.items():
            if bx1 <= ev.x <= bx2 and by1 <= ev.y <= by2:
                handler = {
                    "prev":   self.on_prev,
                    "replay": self.on_replay,
                    "next":   self.on_next,
                }.get(tag)
                self._safe(handler)
                return

    # ------------------------------------------------------------------
    # Painting (delegate to overlay_paint)
    # ------------------------------------------------------------------

    def _draw(self) -> None:
        paint.paint(self)
