"""PySide6 open-source notices viewer.

Parity target: the ``_NoticesViewer`` Toplevel in
``pippal.ui.notices_card``. Read-only scrolling text of the bundled
NOTICES file. The notices-path resolution logic is reused verbatim
from the existing module so both frontends find the same file."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QHBoxLayout,
    QPlainTextEdit,
    QVBoxLayout,
    QWidget,
)

# Reuse the EXISTING resolver so the Qt viewer shows the same file.
from ..ui.notices_card import _resolve_notices_path
from .theme_qt import apply_native_frame
from .widgets_qt import button, separator

__all__ = ["QtNoticesViewer", "resolve_notices_path"]


def resolve_notices_path() -> Path | None:
    return _resolve_notices_path()


class QtNoticesViewer(QWidget):
    def __init__(self, parent: QWidget | None, path: Path | None,
                 brand_name: str) -> None:
        super().__init__(parent, Qt.Window)
        self.path = path
        self.setWindowTitle(f"{brand_name} - Open-source licences")
        self.resize(760, 600)
        self.setMinimumSize(640, 400)

        root = QVBoxLayout(self)
        root.setContentsMargins(20, 18, 20, 0)
        root.setSpacing(0)

        viewer = QPlainTextEdit()
        viewer.setReadOnly(True)
        viewer.setStyleSheet('font-family:"Consolas"; font-size:9pt;')
        viewer.setPlainText(self._load_text())
        root.addWidget(viewer, 1)

        root.addSpacing(10)
        root.addWidget(separator())
        footer = QHBoxLayout()
        footer.setContentsMargins(0, 10, 0, 16)
        footer.addStretch(1)
        footer.addWidget(button("Close", self.close))
        root.addLayout(footer)

    def showEvent(self, event: Any) -> None:
        super().showEvent(event)
        apply_native_frame(self)

    def keyPressEvent(self, event: Any) -> None:
        if event.key() == Qt.Key_Escape:
            self.close()
            return
        super().keyPressEvent(event)

    def _load_text(self) -> str:
        if self.path is None:
            return (
                "Open-source notices were not found.\n\n"
                "Please reinstall PipPal to restore the licences file, "
                "or open docs/THIRD_PARTY.md from the source checkout.")
        try:
            return self.path.read_text(encoding="utf-8")
        except Exception as exc:
            return (
                f"Could not read {self.path}\n\n{exc}\n\n"
                "Please reinstall PipPal to restore the licences file.")
