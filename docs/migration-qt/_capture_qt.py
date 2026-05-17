"""Render the PySide6 windows offscreen and save PNGs for the PR.

Run with the venv python:
  QT_QPA_PLATFORM=offscreen .venv-qt/Scripts/python.exe \
      docs/migration-qt/_capture_qt.py
"""
from __future__ import annotations

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "src"))

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


def _grab(widget, name: str) -> None:
    widget.resize(widget.sizeHint().expandedTo(widget.size()))
    widget.show()
    QApplication.processEvents()
    pix = widget.grab()
    out = os.path.join(HERE, f"qt-{name}.png")
    pix.save(out)
    print(f"saved {out} ({pix.width()}x{pix.height()})")


def main() -> None:
    ensure_dirs()
    app = QApplication.instance() or QApplication(sys.argv)
    apply_app_theme(app)
    cfg = load_config()

    sw = QtSettingsWindow(cfg, on_save=lambda c: None,
                          on_hotkey_change=lambda: [], on_engine_change=None)
    sw.resize(600, 760)
    _grab(sw, "settings")

    vm = QtVoiceManagerDialog(None, on_changed=lambda: None)
    vm.resize(820, 620)
    _grab(vm, "voice-manager")

    ap = QtActivationPanel(cfg, on_play_sample=lambda t: None,
                           on_open_settings=lambda: None,
                           on_open_voice_manager=lambda: None)
    ap.resize(520, 460)
    _grab(ap, "activation-panel")

    nv = QtNoticesViewer(None, resolve_notices_path(), "PipPal")
    nv.resize(760, 600)
    _grab(nv, "notices")

    ov = QtOverlay(cfg)
    ov._set_state("reading")
    ov.start_chunk(
        "PipPal is reading this sentence aloud with a karaoke cursor "
        "that brightens each word as it is spoken.", 6.0, 1, 3)
    ov.show()
    QApplication.processEvents()
    pix = ov.grab()
    out = os.path.join(HERE, "qt-overlay.png")
    pix.save(out)
    print(f"saved {out} ({pix.width()}x{pix.height()})")


if __name__ == "__main__":
    main()
