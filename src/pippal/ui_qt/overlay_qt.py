"""PySide6 reader overlay panel.

Parity target: ``pippal.ui.overlay.Overlay`` + ``overlay_paint``. A
frameless, always-on-top, translucent rounded panel pinned near the
taskbar that renders the current sentence and animates a karaoke
cursor word-by-word, with prev / replay / next / close controls.

The engine talks to this object through the exact same duck-typed
contract it uses for the Tk overlay (``_OverlayProto`` in
``pippal.engine``): ``set_state`` / ``show_message`` /
``set_action_label`` / ``set_paused`` / ``start_chunk``. Every public
entry point marshals onto the Qt GUI thread (the engine calls them
from worker threads) using a queued signal, mirroring the Tk side's
``root.after(0, ...)`` hop.

Word layout + timing reuses ``compute_word_layout`` from the existing
``pippal.ui.overlay_paint`` so the cursor pacing math is identical;
only the drawing backend changes (QPainter instead of a Tk canvas)."""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import Any

from PySide6.QtCore import QPointF, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import (
    QColor,
    QFont,
    QFontMetrics,
    QPainter,
    QPainterPath,
)
from PySide6.QtWidgets import QWidget

from ..config import DEFAULT_CONFIG
from ..timing import (
    OVERLAY_FRAME_MS,
    OVERLAY_HIDE_MIN_MS,
    OVERLAY_MESSAGE_MS,
)
from ..ui.overlay_paint import (
    FADE_SECS,
    FUTURE_RGB,
    PAST_RGB,
    PEAK_RGB,
    WordSpan,
    lerp_rgb,
)


class _QtFontShim:
    """``compute_word_layout`` only needs ``.measure(str) -> int``.

    The existing layout function was written against a Tk font; give
    it the same tiny surface backed by a ``QFontMetrics`` so we can
    reuse the wrapping/timing code unchanged."""

    def __init__(self, font: QFont) -> None:
        self._fm = QFontMetrics(font)

    def measure(self, text: str) -> int:
        return self._fm.horizontalAdvance(text)


def _compute_word_layout_qt(
    text: str, duration: float, bold_font: QFont, width: int,
    padding_x: int, space_w: int,
) -> list[WordSpan]:
    from ..ui.overlay_paint import compute_word_layout
    return compute_word_layout(
        text, duration, _QtFontShim(bold_font), width, padding_x, space_w)


class QtOverlay(QWidget):
    """Frameless karaoke reader panel."""

    WIDTH = 760
    PADDING_X = 32
    PADDING_TOP = 12
    PADDING_BOTTOM = 22
    HEADER_H = 24
    LINE_H = 30
    BODY_TOP_GAP = 4
    BAR_H = 4
    MIN_HEIGHT = 88

    # Thread-safe entrypoints fan in through these signals so the
    # engine's worker threads never touch Qt widgets directly.
    _sig_state = Signal(str)
    _sig_message = Signal(str)
    _sig_action_label = Signal(object)
    _sig_paused = Signal(bool)
    _sig_chunk = Signal(str, float, int, int, float)

    def __init__(
        self,
        config: dict[str, Any],
        on_stop: Callable[[], None] | None = None,
        on_prev: Callable[[], None] | None = None,
        on_replay: Callable[[], None] | None = None,
        on_next: Callable[[], None] | None = None,
    ) -> None:
        super().__init__(None)
        self.config = config
        self.on_stop = on_stop
        self.on_prev = on_prev
        self.on_replay = on_replay
        self.on_next = on_next

        self.setWindowFlags(
            Qt.FramelessWindowHint
            | Qt.WindowStaysOnTopHint
            | Qt.Tool
        )
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setWindowOpacity(0.96)
        self._height = self.MIN_HEIGHT
        self.resize(self.WIDTH, self._height)

        self.font_text = QFont("Segoe UI", 12)
        self.font_text_bold = QFont("Segoe UI Semibold", 12)
        self.font_text_bold.setBold(True)
        self.font_status = QFont("Segoe UI", 9)
        self.font_close = QFont("Segoe UI", 11)
        self._space_w = QFontMetrics(self.font_text).horizontalAdvance(" ")

        self.state = "idle"
        self.message = ""
        self.phase = 0
        self.word_layout: list[WordSpan] = []
        self.line_count = 0
        self.chunk_start_time = 0.0
        self.chunk_duration = 0.0
        self.chunk_idx = 0
        self.chunk_total = 1
        self.action_label: str | None = None
        self.paused = False
        self.paused_elapsed = 0.0
        self._btn_rects: dict[str, tuple[int, int, int, int]] = {}
        self._close_rect = (self.WIDTH - 38, 8, self.WIDTH - 12, 34)

        self._anim = QTimer(self)
        self._anim.setInterval(OVERLAY_FRAME_MS)
        self._anim.timeout.connect(self._tick)
        self._hide_timer = QTimer(self)
        self._hide_timer.setSingleShot(True)
        self._hide_timer.timeout.connect(self._do_hide)

        self._sig_state.connect(self._set_state)
        self._sig_message.connect(self._show_message)
        self._sig_action_label.connect(
            lambda v: setattr(self, "action_label", v))
        self._sig_paused.connect(self._set_paused_impl)
        self._sig_chunk.connect(self._start_chunk_impl)

        self._drag_origin: QPointF | None = None

    # ------------------------------------------------------------------
    # Engine-facing API (thread-safe — matches pippal.engine._OverlayProto)
    # ------------------------------------------------------------------

    def set_state(self, state: str) -> None:
        self._sig_state.emit(state)

    def show_message(self, msg: str) -> None:
        self._sig_message.emit(msg)

    def set_action_label(self, label: str | None) -> None:
        self._sig_action_label.emit(label)

    def set_paused(self, paused: bool) -> None:
        self._sig_paused.emit(bool(paused))

    def start_chunk(self, text: str, duration: float, idx: int = 0,
                    total: int = 1, offset_s: float = 0.0) -> None:
        self._sig_chunk.emit(text, float(duration), int(idx),
                             int(total), float(offset_s))

    def hide_panel(self) -> None:
        self._do_hide()

    # ------------------------------------------------------------------
    # GUI-thread implementations
    # ------------------------------------------------------------------

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
            self._hide_timer.stop()
            self._show()
            if not self._anim.isActive():
                self._anim.start()
        elif state == "done":
            self._hide_timer.stop()
            self.update()
            delay = max(OVERLAY_HIDE_MIN_MS, int(self.config.get(
                "auto_hide_ms", DEFAULT_CONFIG["auto_hide_ms"])))
            self._hide_timer.start(delay)
        else:
            self._do_hide()

    def _show_message(self, msg: str) -> None:
        if not self.config.get("show_overlay", True):
            return
        self.message = msg
        self.state = "done"
        self._hide_timer.stop()
        self._show()
        self.update()
        self._hide_timer.start(OVERLAY_MESSAGE_MS)

    def _set_paused_impl(self, paused: bool) -> None:
        if paused and not self.paused:
            self.paused_elapsed = max(0.0, time.time() - self.chunk_start_time)
            self.paused = True
        elif (not paused) and self.paused:
            self.chunk_start_time = time.time() - self.paused_elapsed
            self.paused = False
        self.update()

    def _start_chunk_impl(self, text: str, duration: float, idx: int,
                          total: int, offset_s: float) -> None:
        self.chunk_idx = idx
        self.chunk_total = total
        self.word_layout = _compute_word_layout_qt(
            text, duration, self.font_text_bold,
            self.WIDTH, self.PADDING_X, self._space_w)
        self.line_count = (self.word_layout[-1].y + 1) if self.word_layout else 1
        if self.word_layout:
            self.chunk_duration = duration
            self.chunk_start_time = time.time() + offset_s
            self._set_height(self._compute_height(self.line_count))
        else:
            self._set_height(self.MIN_HEIGHT)
        self.update()

    def _compute_height(self, lines: int) -> int:
        return (self.PADDING_TOP + self.HEADER_H + self.BODY_TOP_GAP
                + lines * self.LINE_H + 6 + self.BAR_H + self.PADDING_BOTTOM)

    def _set_height(self, h: int) -> None:
        h = int(h)
        if h == self._height:
            return
        self._height = h
        self.resize(self.WIDTH, h)
        if self.isVisible():
            self._show()

    def _show(self) -> None:
        screen = self.screen() or (
            self.windowHandle().screen() if self.windowHandle() else None)
        geo = screen.availableGeometry() if screen else None
        if geo is not None:
            sw, sh = geo.width(), geo.height()
            sx, sy = geo.x(), geo.y()
        else:
            sw, sh, sx, sy = 1920, 1080, 0, 0
        x = sx + (sw - self.WIDTH) // 2
        y = sy + sh - self._height - int(self.config.get(
            "overlay_y_offset", DEFAULT_CONFIG["overlay_y_offset"]))
        self.move(x, y)
        if not self.isVisible():
            self.show()
        self.raise_()

    def _do_hide(self) -> None:
        self._hide_timer.stop()
        self._anim.stop()
        self.word_layout = []
        self.line_count = 0
        self.action_label = None
        self._set_height(self.MIN_HEIGHT)
        self.hide()

    def _tick(self) -> None:
        self.phase += 1
        self.update()

    def _now_relative(self) -> float:
        if self.paused:
            return self.paused_elapsed
        return time.time() - self.chunk_start_time

    # ------------------------------------------------------------------
    # Mouse handling — close + prev/replay/next hit-rects, right-drag move
    # ------------------------------------------------------------------

    def mousePressEvent(self, event: Any) -> None:
        if event.button() == Qt.RightButton:
            self._drag_origin = event.globalPosition() - QPointF(
                self.x(), self.y())
            return
        if event.button() != Qt.LeftButton:
            return
        x, y = event.position().x(), event.position().y()
        cx1, cy1, cx2, cy2 = self._close_rect
        if cx1 <= x <= cx2 and cy1 <= y <= cy2:
            self._safe(self.on_stop)
            return
        for tag, (bx1, by1, bx2, by2) in self._btn_rects.items():
            if bx1 <= x <= bx2 and by1 <= y <= by2:
                handler = {"prev": self.on_prev, "replay": self.on_replay,
                           "next": self.on_next}.get(tag)
                self._safe(handler)
                return

    def mouseMoveEvent(self, event: Any) -> None:
        if self._drag_origin is not None and (event.buttons() & Qt.RightButton):
            new = event.globalPosition() - self._drag_origin
            self.move(int(new.x()), int(new.y()))

    def mouseReleaseEvent(self, event: Any) -> None:
        if event.button() == Qt.RightButton:
            self._drag_origin = None

    @staticmethod
    def _safe(handler: Callable[[], None] | None) -> None:
        if handler is None:
            return
        try:
            handler()
        except Exception as e:
            import sys
            print(f"[overlay-qt] click handler failed: {e}", file=sys.stderr)

    # ------------------------------------------------------------------
    # Painting (QPainter port of overlay_paint.paint)
    # ------------------------------------------------------------------

    def paintEvent(self, _event: Any) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        p.setRenderHint(QPainter.TextAntialiasing, True)

        path = QPainterPath()
        path.addRoundedRect(QRectF(1, 1, self.WIDTH - 2,
                                   self._height - 2), 14, 14)
        p.fillPath(path, QColor("#13151c"))
        pen = p.pen()
        pen.setColor(QColor("#262a3a"))
        pen.setWidth(1)
        p.setPen(pen)
        p.drawPath(path)

        self._paint_header(p)
        if self.paused and self.state == "reading":
            self._paint_paused_chip(p)

        show_text = self.config.get("show_text_in_overlay", True)
        if self.state == "reading" and self.word_layout and show_text:
            self._paint_text_body(p)
            self._paint_progress(p)
        elif self.state == "reading":
            self._paint_center_text(p, "reading…", "#9aa0b8")
            self._paint_progress(p)
        elif self.state == "thinking":
            self._paint_thinking(p)
        elif self.state == "done" and self.message:
            self._paint_center_text(p, self.message, "#9aa0b8")
        p.end()

    def _paint_header(self, p: QPainter) -> None:
        import math
        if self.state == "thinking":
            dot, r = "#5b8def", 4 + math.sin(self.phase * 0.25) * 1.4
        elif self.state == "reading":
            dot, r = "#6dd9b8", 4
        else:
            dot, r = "#5a5e74", 3.5
        y = 20
        dot_x = self.PADDING_X
        p.setBrush(QColor(dot))
        p.setPen(Qt.NoPen)
        p.drawEllipse(QPointF(dot_x, y), r, r)

        brand = self.config.get("brand_name", "PipPal")
        label = (f"{brand}  ·  {self.action_label}"
                 if self.action_label else brand)
        p.setPen(QColor("#7d8398"))
        p.setFont(self.font_status)
        p.drawText(QRectF(dot_x + 12, y - 10, self.WIDTH, 20),
                   Qt.AlignVCenter | Qt.AlignLeft, label)

        bx = self.WIDTH - 25
        p.setBrush(QColor("#1c1f2c"))
        p.setPen(Qt.NoPen)
        p.drawEllipse(QPointF(bx, y), 11, 11)
        p.setPen(QColor("#7d8398"))
        p.setFont(self.font_close)
        p.drawText(QRectF(bx - 11, y - 11, 22, 22), Qt.AlignCenter, "✕")

    def _paint_paused_chip(self, p: QPainter) -> None:
        chip_w, chip_h = 64, 18
        chip_x = (self.WIDTH - chip_w) // 2
        chip_y = self.PADDING_TOP + self.HEADER_H - 4
        path = QPainterPath()
        path.addRoundedRect(QRectF(chip_x, chip_y, chip_w, chip_h), 8, 8)
        p.fillPath(path, QColor("#3a2f1f"))
        p.setPen(QColor("#a07a3a"))
        p.drawPath(path)
        p.setPen(QColor("#e8c787"))
        f = QFont("Segoe UI Semibold", 9)
        f.setBold(True)
        p.setFont(f)
        p.drawText(QRectF(chip_x, chip_y, chip_w, chip_h),
                   Qt.AlignCenter, "paused")

    def _paint_text_body(self, p: QPainter) -> None:
        elapsed = self._now_relative()
        layout = self.word_layout
        cur = 0
        for i, w in enumerate(layout):
            if elapsed >= w.ts:
                cur = i
            else:
                break
        body_top = self.PADDING_TOP + self.HEADER_H + self.BODY_TOP_GAP
        for i, w in enumerate(layout):
            py = body_top + w.y * self.LINE_H + (self.LINE_H - 22) // 2
            color, bold = self._word_appearance(i, cur, elapsed, w)
            p.setPen(QColor(color))
            p.setFont(self.font_text_bold if bold else self.font_text)
            p.drawText(QPointF(self.PADDING_X + w.x,
                               py + 18), w.word)

    @staticmethod
    def _word_appearance(i: int, cur: int, elapsed: float,
                         w: WordSpan) -> tuple[str, bool]:
        def hexs(rgb: tuple[int, int, int]) -> str:
            return f"#{rgb[0]:02x}{rgb[1]:02x}{rgb[2]:02x}"
        if i == cur:
            return hexs(PEAK_RGB), True
        if elapsed >= w.te:
            k = max(0.0, 1.0 - (elapsed - w.te) / FADE_SECS)
            return hexs(lerp_rgb(PAST_RGB, PEAK_RGB, k)), False
        k = max(0.0, 1.0 - (w.ts - elapsed) / FADE_SECS)
        return hexs(lerp_rgb(FUTURE_RGB, PEAK_RGB, k)), False

    def _paint_progress(self, p: QPainter) -> None:
        elapsed = max(0.0, self._now_relative())
        dur = self.chunk_duration if self.chunk_duration > 0 else 1.0
        prog = max(0.0, min(1.0, elapsed / dur))
        row_y = self._height - self.PADDING_BOTTOM + 4
        center_y = row_y + 8
        self._btn_rects = {}
        specs = [("prev", "⏮"), ("replay", "⟲"), ("next", "⏭")]
        btn_size, btn_gap = 22, 4
        x = self.PADDING_X
        p.setFont(QFont("Segoe UI Symbol", 11))
        p.setPen(QColor("#9aa0b8"))
        for tag, glyph in specs:
            p.drawText(QRectF(x, row_y - 4, btn_size, btn_size),
                       Qt.AlignCenter, glyph)
            self._btn_rects[tag] = (x, row_y - 4, x + btn_size,
                                    row_y + btn_size - 4)
            x += btn_size + btn_gap
        bar_left = x + 6
        counter_w = 0
        if self.chunk_total and self.chunk_total > 1:
            label = f"{self.chunk_idx + 1}/{self.chunk_total}"
            p.setPen(QColor("#7d8398"))
            p.setFont(self.font_status)
            fm = QFontMetrics(self.font_status)
            p.drawText(QRectF(self.WIDTH - self.PADDING_X - 80,
                              center_y - 10, 80, 20),
                       Qt.AlignRight | Qt.AlignVCenter, label)
            counter_w = fm.horizontalAdvance(label) + 10
        bar_right = self.WIDTH - self.PADDING_X - counter_w
        bar_y = center_y - self.BAR_H // 2
        if bar_right > bar_left + 10:
            p.fillRect(QRectF(bar_left, bar_y, bar_right - bar_left,
                              self.BAR_H), QColor("#1f2230"))
            if self.chunk_duration > 0:
                p.fillRect(QRectF(bar_left, bar_y,
                                  (bar_right - bar_left) * prog,
                                  self.BAR_H), QColor("#6dd9b8"))

    def _paint_thinking(self, p: QPainter) -> None:
        import math
        cy = (self.PADDING_TOP + self.HEADER_H + self._height) // 2
        p.setPen(Qt.NoPen)
        for i in range(3):
            bx = self.WIDTH // 2 - 16 + i * 16
            a = math.sin(self.phase * 0.22 + i) * 0.5 + 0.5
            r = 2.5 + a * 2.5
            sr = min(int(91 + a * 70), 255)
            sg = min(int(141 + a * 70), 255)
            p.setBrush(QColor(sr, sg, 239))
            p.drawEllipse(QPointF(bx, cy), r, r)
        label = self.action_label or "preparing…"
        p.setPen(QColor("#7d8398"))
        p.setFont(self.font_status)
        p.drawText(QRectF(0, cy + 8, self.WIDTH, 20),
                   Qt.AlignCenter, label)

    def _paint_center_text(self, p: QPainter, text: str, color: str) -> None:
        cy = (self.PADDING_TOP + self.HEADER_H + self._height) // 2
        p.setPen(QColor(color))
        p.setFont(self.font_text)
        p.drawText(QRectF(0, cy - 12, self.WIDTH, 24),
                   Qt.AlignCenter, text)
