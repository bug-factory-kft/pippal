"""Drawing routines for the reader-panel overlay.

Module-level functions that paint onto the overlay's canvas. Pulled out
of `overlay.py` so the lifecycle code (state machine, scheduling, click
handling) stays on one screen and the painting code stays on another.

All drawing functions take the Overlay-shaped object as `o` and render
into `o.canvas`. They never mutate state — that's `overlay.py`'s job."""

from __future__ import annotations

import math
import tkinter as tk
from dataclasses import dataclass
from tkinter import font as tkfont
from typing import Any, Protocol

from ..text_utils import iter_word_spans, word_timing_weight

# ---------- types ----------

@dataclass(slots=True)
class WordSpan:
    """One word's geometry + timing in the karaoke layout."""
    word: str
    x: int        # x-pixel offset within the text area, line-relative
    y: int        # line index (0-based)
    w: int        # rendered pixel width (with bold font)
    ts: float     # time when this word starts being spoken (seconds into chunk)
    te: float     # time when this word ends


# ---------- colour stops + helpers ----------

PAST_RGB: tuple[int, int, int] = (0x60, 0x65, 0x7a)     # cooled, dim
FUTURE_RGB: tuple[int, int, int] = (0xc8, 0xcd, 0xe0)    # light, slightly muted
PEAK_RGB: tuple[int, int, int] = (0xff, 0xff, 0xff)      # bright white at the cursor
FADE_SECS: float = 0.50                                  # how long colour bleeds before/after


def smoothstep(t: float) -> float:
    t = 0.0 if t < 0 else (1.0 if t > 1 else t)
    return t * t * (3 - 2 * t)


def lerp_rgb(
    a: tuple[int, int, int],
    b: tuple[int, int, int],
    t: float,
) -> tuple[int, int, int]:
    t = smoothstep(t)
    return (
        int(a[0] + (b[0] - a[0]) * t),
        int(a[1] + (b[1] - a[1]) * t),
        int(a[2] + (b[2] - a[2]) * t),
    )


def hex_color(rgb: tuple[int, int, int]) -> str:
    return f"#{rgb[0]:02x}{rgb[1]:02x}{rgb[2]:02x}"


def round_rect(
    c: tk.Canvas, x1: float, y1: float, x2: float, y2: float, r: float, **kw: Any,
) -> int:
    pts = [
        x1 + r, y1, x2 - r, y1, x2, y1, x2, y1 + r,
        x2, y2 - r, x2, y2, x2 - r, y2, x1 + r, y2,
        x1, y2, x1, y2 - r, x1, y1 + r, x1, y1,
    ]
    return c.create_polygon(pts, smooth=True, **kw)


# ---------- layout ----------

def compute_word_layout(
    text: str,
    duration: float,
    font_text_bold: tkfont.Font,
    width: int,
    padding_x: int,
    space_w: int,
) -> list[WordSpan]:
    """Lay out `text` into `WordSpan`s for an overlay of given geometry.

    Each word is positioned at an `x, y` offset within a body of width
    `width - 2*padding_x`, wrapping when a word would overflow.
    Word timing is interpolated linearly across the chunk duration,
    weighted by syllable count.

    Returns an empty list if the text has no words or duration <= 0."""
    words = list(iter_word_spans(text))
    if not words or duration <= 0:
        return []

    weights = [word_timing_weight(m.group()) for m in words]
    total_weight = sum(weights) or 1.0
    head = min(0.12, duration * 0.05)
    tail = min(0.12, duration * 0.05)
    usable = max(0.1, duration - head - tail)

    avail = width - 2 * padding_x
    layout: list[WordSpan] = []
    accum_w = 0.0
    x = 0
    line = 0
    for m, weight in zip(words, weights):
        wt = m.group()
        wpx = font_text_bold.measure(wt)
        if x > 0 and x + wpx > avail:
            line += 1
            x = 0
        ts = head + (accum_w / total_weight) * usable
        accum_w += weight
        te = head + (accum_w / total_weight) * usable
        layout.append(WordSpan(word=wt, x=x, y=line, w=wpx, ts=ts, te=te))
        x += wpx + space_w
    return layout


# ---------- the Overlay duck-type the paint functions consume ----------

class _OverlayLike(Protocol):
    """Minimal surface a paintable overlay must expose."""

    canvas: tk.Canvas
    config: dict[str, Any]
    state: str
    message: str
    phase: int

    paused: bool
    paused_elapsed: float
    chunk_start_time: float
    chunk_duration: float
    chunk_idx: int
    chunk_total: int
    action_label: str | None

    word_layout: list[WordSpan]
    line_count: int

    font_text: tkfont.Font
    font_text_bold: tkfont.Font
    font_status: tkfont.Font
    font_close: tkfont.Font

    WIDTH: int
    PADDING_X: int
    PADDING_TOP: int
    PADDING_BOTTOM: int
    HEADER_H: int
    LINE_H: int
    BODY_TOP_GAP: int
    BAR_H: int

    # Set by paint_progress() so the click handler can hit-test buttons.
    _btn_rects: dict[str, tuple[int, int, int, int]]
    _height: int


# ---------- top-level paint dispatcher ----------

def paint(o: _OverlayLike) -> None:
    """Re-render the entire overlay canvas based on `o`'s current state."""
    c = o.canvas
    c.delete("all")
    round_rect(c, 1, 1, o.WIDTH - 1, o._height - 1, 14,
               fill="#13151c", outline="#262a3a", width=1)
    paint_header(o)

    if o.paused and o.state == "reading":
        _paint_paused_chip(o)

    show_text = o.config.get("show_text_in_overlay", True)
    if o.state == "reading" and o.word_layout and show_text:
        paint_text_body(o)
        paint_progress(o)
    elif o.state == "reading":
        paint_center_text(o, "reading…", "#9aa0b8")
        paint_progress(o)
    elif o.state == "thinking":
        paint_thinking_dots(o)
        paint_thinking_label(o)
    elif o.state == "done" and o.message:
        # Empty done state used to show a "✓" — that read as gimmicky,
        # so we now just let the panel fade out silently.
        paint_center_text(o, o.message, "#9aa0b8")


# ---------- region painters ----------

def paint_header(o: _OverlayLike) -> None:
    c = o.canvas
    if o.state == "thinking":
        dot, r = "#5b8def", 4 + math.sin(o.phase * 0.25) * 1.4
    elif o.state == "reading":
        dot, r = "#6dd9b8", 4
    else:
        dot, r = "#5a5e74", 3.5

    y = 20

    # Brand logo on the far left (when available). The state dot and
    # text shift right to make room. Falls back to the dot-only
    # layout if the asset failed to load.
    logo_photo = getattr(o, "logo_photo", None)
    if logo_photo is not None:
        c.create_image(o.PADDING_X, y, anchor="w", image=logo_photo)
        dot_x = o.PADDING_X + 26  # 18 px logo + 8 px gap
    else:
        dot_x = o.PADDING_X
    c.create_oval(dot_x - r, y - r, dot_x + r, y + r,
                  fill=dot, outline="")

    brand = o.config.get("brand_name", "PipPal")
    label = f"{brand}  ·  {o.action_label}" if o.action_label else brand
    c.create_text(dot_x + 12, y, anchor="w", text=label,
                  fill="#7d8398", font=o.font_status)

    bx = o.WIDTH - 25
    c.create_oval(bx - 11, y - 11, bx + 11, y + 11, fill="#1c1f2c", outline="")
    c.create_text(bx, y, text="✕", fill="#7d8398", font=o.font_close)


def _paint_paused_chip(o: _OverlayLike) -> None:
    chip_w, chip_h = 64, 18
    chip_x = (o.WIDTH - chip_w) // 2
    chip_y = o.PADDING_TOP + o.HEADER_H - 4
    round_rect(o.canvas, chip_x, chip_y, chip_x + chip_w, chip_y + chip_h, 8,
               fill="#3a2f1f", outline="#a07a3a", width=1)
    o.canvas.create_text(chip_x + chip_w / 2, chip_y + chip_h / 2,
                         text="paused", fill="#e8c787",
                         font=("Segoe UI Semibold", 9))


def paint_text_body(o: _OverlayLike) -> None:
    if not o.word_layout:
        return
    elapsed = _now_relative(o)
    layout = o.word_layout

    cur = 0
    for i, w in enumerate(layout):
        if elapsed >= w.ts:
            cur = i
        else:
            break

    body_top = o.PADDING_TOP + o.HEADER_H + o.BODY_TOP_GAP
    for i, w in enumerate(layout):
        py = body_top + w.y * o.LINE_H + (o.LINE_H - 22) // 2
        color, font = _word_appearance(i, cur, elapsed, w,
                                        o.font_text, o.font_text_bold)
        o.canvas.create_text(o.PADDING_X + w.x, py,
                             text=w.word, anchor="nw", fill=color, font=font)


def _word_appearance(
    i: int, cur: int, elapsed: float, w: WordSpan,
    font_regular: tkfont.Font, font_bold: tkfont.Font,
) -> tuple[str, tkfont.Font]:
    """Colour + font for a word given its temporal distance from the cursor."""
    if i == cur:
        return hex_color(PEAK_RGB), font_bold
    if elapsed >= w.te:
        k = max(0.0, 1.0 - (elapsed - w.te) / FADE_SECS)
        return hex_color(lerp_rgb(PAST_RGB, PEAK_RGB, k)), font_regular
    k = max(0.0, 1.0 - (w.ts - elapsed) / FADE_SECS)
    return hex_color(lerp_rgb(FUTURE_RGB, PEAK_RGB, k)), font_regular


def paint_progress(o: _OverlayLike) -> None:
    """Draw the bottom row: prev/replay/next buttons, progress bar, chunk
    counter. Records button hit-rects on `o._btn_rects` for click dispatch."""
    c = o.canvas
    elapsed = max(0.0, _now_relative(o))
    dur = o.chunk_duration if o.chunk_duration > 0 else 1.0
    prog = max(0.0, min(1.0, elapsed / dur))

    row_y = o._height - o.PADDING_BOTTOM + 4
    center_y = row_y + 8

    o._btn_rects = {}
    button_specs = [("prev", "⏮"), ("replay", "⟲"), ("next", "⏭")]
    btn_size, btn_gap = 22, 4
    x = o.PADDING_X
    font_btn = ("Segoe UI Symbol", 11)
    for tag, glyph in button_specs:
        x1, y1 = x, row_y - 4
        x2, y2 = x + btn_size, row_y + btn_size - 4
        c.create_text(x + btn_size / 2, center_y, text=glyph,
                      fill="#9aa0b8", font=font_btn, tags=(f"btn_{tag}",))
        o._btn_rects[tag] = (x1, y1, x2, y2)
        x += btn_size + btn_gap

    bar_left = x + 6

    counter_w = 0
    if o.chunk_total and o.chunk_total > 1:
        label = f"{o.chunk_idx + 1}/{o.chunk_total}"
        c.create_text(o.WIDTH - o.PADDING_X, center_y,
                      anchor="e", text=label, fill="#7d8398",
                      font=o.font_status)
        counter_w = o.font_status.measure(label) + 10

    bar_right = o.WIDTH - o.PADDING_X - counter_w
    bar_y = center_y - o.BAR_H // 2
    if bar_right > bar_left + 10:
        c.create_rectangle(bar_left, bar_y, bar_right, bar_y + o.BAR_H,
                           fill="#1f2230", outline="")
        if o.chunk_duration > 0:
            c.create_rectangle(
                bar_left, bar_y,
                bar_left + (bar_right - bar_left) * prog,
                bar_y + o.BAR_H,
                fill="#6dd9b8", outline="",
            )


def paint_thinking_dots(o: _OverlayLike) -> None:
    cy = (o.PADDING_TOP + o.HEADER_H + o._height) // 2
    for i in range(3):
        bx = o.WIDTH // 2 - 16 + i * 16
        a = (math.sin(o.phase * 0.22 + i * 1.0) * 0.5 + 0.5)
        r = 2.5 + a * 2.5
        sr = min(int(91 + a * 70), 255)
        sg = min(int(141 + a * 70), 255)
        sb = 239
        col = f"#{sr:02x}{sg:02x}{sb:02x}"
        o.canvas.create_oval(bx - r, cy - r, bx + r, cy + r, fill=col, outline="")


def paint_thinking_label(o: _OverlayLike) -> None:
    """Small caption below the bouncing dots so the user can see what
    the app is actually doing while it spins (synthesizing, preparing
    an AI rewrite, etc.)."""
    label = o.action_label or "preparing…"
    cy = (o.PADDING_TOP + o.HEADER_H + o._height) // 2
    o.canvas.create_text(o.WIDTH // 2, cy + 18, text=label,
                         fill="#7d8398", font=o.font_status)


def paint_center_text(o: _OverlayLike, text: str, color: str) -> None:
    cy = (o.PADDING_TOP + o.HEADER_H + o._height) // 2
    o.canvas.create_text(o.WIDTH // 2, cy, text=text, fill=color,
                         font=o.font_text)


def _now_relative(o: _OverlayLike) -> float:
    """Seconds since the chunk's effective start, frozen while paused."""
    import time
    if o.paused:
        return o.paused_elapsed
    return time.time() - o.chunk_start_time
