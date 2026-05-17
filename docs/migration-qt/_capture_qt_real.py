"""Render the PySide6 windows on the real Windows display and save PNGs.

Run with the venv python (NO QT_QPA_PLATFORM override):
  .venv-qt/Scripts/python.exe docs/migration-qt/_capture_qt_real.py
"""
from __future__ import annotations

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "src"))

from PySide6.QtCore import QTimer  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from pippal.config import load_config  # noqa: E402
from pippal.paths import ensure_dirs  # noqa: E402
from pippal.ui_qt import (  # noqa: E402
    QtActivationPanel,
    QtOverlay,
    QtSettingsWindow,
    QtVoiceManagerDialog,
    apply_app_theme,
)
from pippal.ui_qt.notices_qt import QtNoticesViewer, resolve_notices_path  # noqa: E402


def main() -> None:
    ensure_dirs()
    app = QApplication.instance() or QApplication(sys.argv)
    apply_app_theme(app)
    cfg = load_config()

    sw = QtSettingsWindow(cfg, on_save=lambda c: None,
                          on_hotkey_change=lambda: [], on_engine_change=None)
    sw.resize(600, 760)
    sw.show()

    vm = QtVoiceManagerDialog(None, on_changed=lambda: None)
    vm.resize(820, 620)
    vm.show()

    ap = QtActivationPanel(cfg, on_play_sample=lambda t: None,
                           on_open_settings=lambda: None,
                           on_open_voice_manager=lambda: None)
    ap.resize(520, 470)
    ap.show()

    nv = QtNoticesViewer(None, resolve_notices_path(), "PipPal")
    nv.resize(760, 600)
    nv.show()

    ov = QtOverlay(cfg)
    ov._set_state("reading")
    ov.start_chunk(
        "PipPal is reading this sentence aloud with a karaoke cursor "
        "that brightens each word as it is spoken.", 6.0, 1, 3)
    ov.show()

    shots = [
        (sw, "qt-settings.png"),
        (vm, "qt-voice-manager.png"),
        (ap, "qt-activation-panel.png"),
        (nv, "qt-notices.png"),
        (ov, "qt-overlay.png"),
    ]

    def grab_all() -> None:
        for w, name in shots:
            w.raise_()
            w.activateWindow()
            QApplication.processEvents()
            pix = w.grab()
            out = os.path.join(HERE, name)
            pix.save(out)
            print(f"saved {out} ({pix.width()}x{pix.height()})")
        app.quit()

    QTimer.singleShot(1200, grab_all)
    app.exec()


if __name__ == "__main__":
    main()
