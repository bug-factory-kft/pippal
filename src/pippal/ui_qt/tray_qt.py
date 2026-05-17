"""QSystemTrayIcon for the PySide6 frontend.

Parity target: the pystray tray composed in ``pippal.app`` from the
``_register.py`` builders — Recent submenu (last 10 readings + Clear
history), Settings…, First-run check, Quit, plus the idle/speaking
icon swap. We reuse the existing ``pippal.tray.make_tray_icon`` PIL
factory and convert it to a ``QIcon`` so the tray art is byte-for-byte
the same as the Tk build's. Single left-click opens Settings (the Tk
build's ``default=True`` item)."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from PySide6.QtGui import QIcon, QPixmap
from PySide6.QtWidgets import QMenu, QSystemTrayIcon

from ..tray import make_tray_icon


def _pil_to_qicon(speaking: bool) -> QIcon:
    img = make_tray_icon(speaking).convert("RGBA")
    data = img.tobytes("raw", "RGBA")
    from PySide6.QtGui import QImage
    qimg = QImage(data, img.width, img.height, QImage.Format_RGBA8888)
    return QIcon(QPixmap.fromImage(qimg))


class QtTray:
    def __init__(
        self,
        *,
        brand: str,
        engine: Any,
        on_settings: Callable[[], None],
        on_first_run_check: Callable[[], None],
        on_quit: Callable[[], None],
    ) -> None:
        self._brand = brand
        self._engine = engine
        self._on_settings = on_settings
        self._on_first_run_check = on_first_run_check
        self._on_quit = on_quit
        self._speaking = False

        self._icon_idle = _pil_to_qicon(False)
        self._icon_speaking = _pil_to_qicon(True)

        self.tray = QSystemTrayIcon(self._icon_idle)
        self.tray.setToolTip(brand)
        self._menu = QMenu()
        self._menu.aboutToShow.connect(self._rebuild_menu)
        self.tray.setContextMenu(self._menu)
        self.tray.activated.connect(self._on_activated)
        self._rebuild_menu()
        self.tray.show()

    def _on_activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        # Single left click -> Settings, mirroring pystray default item.
        if reason in (QSystemTrayIcon.Trigger, QSystemTrayIcon.DoubleClick):
            self._on_settings()

    def _rebuild_menu(self) -> None:
        """Rebuilt every time the menu opens so Recent stays fresh —
        same contract as the pystray history submenu builder."""
        self._menu.clear()

        recent = self._menu.addMenu("Recent")
        items = self._engine.get_history()
        if not items:
            empty = recent.addAction("(empty)")
            empty.setEnabled(False)
        else:
            for text in items[:10]:
                preview = text.replace("\n", " ").strip()
                if len(preview) > 70:
                    preview = preview[:67] + "…"
                act = recent.addAction(preview)
                act.triggered.connect(
                    lambda _checked=False, t=text:
                    self._engine.replay_text(t))
            recent.addSeparator()
            clear = recent.addAction("Clear history")
            clear.triggered.connect(
                lambda _checked=False: self._engine.clear_history())

        self._menu.addSeparator()
        fr = self._menu.addAction("First-run check")
        fr.triggered.connect(lambda _checked=False: self._on_first_run_check())
        st = self._menu.addAction("Settings…")
        st.triggered.connect(lambda _checked=False: self._on_settings())
        self._menu.addSeparator()
        q = self._menu.addAction("Quit")
        q.triggered.connect(lambda _checked=False: self._on_quit())

    def update_speaking(self, speaking: bool) -> None:
        if speaking == self._speaking:
            return
        self._speaking = speaking
        self.tray.setIcon(
            self._icon_speaking if speaking else self._icon_idle)
        self.tray.setToolTip(
            f"{self._brand} — speaking" if speaking else self._brand)

    def stop(self) -> None:
        try:
            self.tray.hide()
        except Exception:
            pass
