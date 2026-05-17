"""PySide6 Voice Manager — install/remove curated Piper voices.

Parity target: ``pippal.ui.voice_manager.VoiceManagerDialog``. Same
catalogue source (``plugins.voices()``), same Language/Quality/Status
filters + free-text Search, same per-row Install/Remove, same
background download (reusing ``install_piper_voice`` from the existing
module — the actual download code is NOT reimplemented), same
on_changed/on_installed callbacks, same Close."""

from __future__ import annotations

import threading
from collections.abc import Callable
from typing import Any

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from .. import plugins
from ..paths import VOICES_DIR

# Reuse the EXISTING download/install backend untouched.
from ..ui.voice_manager import install_piper_voice
from ..voices import (
    PiperVoice,
    installed_voices,
    locale_name,
    voice_filename,
)
from .theme_qt import apply_native_frame
from .widgets_qt import (
    button,
    card_label,
    danger_button,
    hint_label,
    make_card,
    separator,
)


class QtVoiceManagerDialog(QWidget):

    _install_done = Signal(str, bool, str)  # voice_id, ok, error

    def __init__(
        self,
        parent: QWidget | None,
        on_changed: Callable[[], None],
        *,
        on_installed: Callable[[str], None] | None = None,
    ) -> None:
        super().__init__(parent, Qt.Window)
        self.on_changed = on_changed
        self.on_installed = on_installed
        self.row_status: dict[str, QLabel] = {}
        self.row_buttons: dict[str, QWidget] = {}
        self._voice_by_id: dict[str, PiperVoice] = {}

        self._all_voices: list[PiperVoice] = sorted(
            plugins.voices(),
            key=lambda v: (locale_name(v["lang"]), v["id"]),
        )

        self.setWindowTitle("Voices")
        self.resize(820, 620)
        self.setMinimumSize(760, 520)
        self._install_done.connect(self._on_install_done)

        self._filter_timer = QTimer(self)
        self._filter_timer.setSingleShot(True)
        self._filter_timer.setInterval(400)
        self._filter_timer.timeout.connect(self._apply_filter)

        self._build()
        self._apply_filter()

    def showEvent(self, event: Any) -> None:
        super().showEvent(event)
        apply_native_frame(self)

    def keyPressEvent(self, event: Any) -> None:
        if event.key() == Qt.Key_Escape:
            self.close()
            return
        super().keyPressEvent(event)

    def _build(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        filter_bar = QWidget()
        fb = QVBoxLayout(filter_bar)
        fb.setContentsMargins(20, 20, 20, 0)
        fb.setSpacing(10)

        row1 = QHBoxLayout()
        row1.setSpacing(8)
        row1.addWidget(card_label("Language"))
        unique_locales = sorted({v["lang"] for v in self._all_voices},
                                key=locale_name)
        self._lang_choices: list[tuple[str, str]] = [
            ("__all__", "All languages")
        ] + [(code, locale_name(code)) for code in unique_locales]
        self.lang_combo = QComboBox()
        self.lang_combo.addItems([label for _c, label in self._lang_choices])
        self.lang_combo.currentTextChanged.connect(lambda _t: self._apply_filter())
        row1.addWidget(self.lang_combo)
        row1.addSpacing(12)

        row1.addWidget(card_label("Quality"))
        self.quality_combo = QComboBox()
        self.quality_combo.addItems(["Any", "high", "medium", "low", "x_low"])
        self.quality_combo.currentTextChanged.connect(lambda _t: self._apply_filter())
        row1.addWidget(self.quality_combo)
        row1.addSpacing(12)

        row1.addWidget(card_label("Status"))
        self.status_combo = QComboBox()
        self.status_combo.addItems(["Any", "Installed", "Not installed"])
        self.status_combo.currentTextChanged.connect(lambda _t: self._apply_filter())
        row1.addWidget(self.status_combo)
        row1.addStretch(1)
        fb.addLayout(row1)

        row2 = QHBoxLayout()
        row2.setSpacing(8)
        slbl = card_label("Search")
        slbl.setFixedWidth(70)
        row2.addWidget(slbl)
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("Filter by name, id, or label…")
        self.search_edit.textChanged.connect(lambda _t: self._filter_timer.start())
        self.search_edit.returnPressed.connect(self._apply_filter)
        row2.addWidget(self.search_edit, 1)
        fb.addLayout(row2)
        root.addWidget(filter_bar)

        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._rows_host = QWidget()
        self._rows_layout = QVBoxLayout(self._rows_host)
        self._rows_layout.setContentsMargins(20, 8, 20, 8)
        self._rows_layout.setSpacing(10)
        self._scroll.setWidget(self._rows_host)
        root.addWidget(self._scroll, 1)

        root.addWidget(separator())
        footer = QHBoxLayout()
        footer.setContentsMargins(24, 12, 24, 16)
        footer.addStretch(1)
        footer.addWidget(button("Close", self.close))
        root.addLayout(footer)

    def _clear_rows(self) -> None:
        self.row_status.clear()
        self.row_buttons.clear()
        while self._rows_layout.count():
            item = self._rows_layout.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()

    def _apply_filter(self) -> None:
        self._clear_rows()
        chosen_label = self.lang_combo.currentText()
        chosen_code = "__all__"
        for code, label in self._lang_choices:
            if label == chosen_label:
                chosen_code = code
                break
        chosen_quality = self.quality_combo.currentText()
        chosen_status = self.status_combo.currentText()
        query = self.search_edit.text().strip().lower()

        installed = set(installed_voices())
        rows = 0
        for v in self._all_voices:
            if chosen_code != "__all__" and v["lang"] != chosen_code:
                continue
            if chosen_quality != "Any" and v["quality"] != chosen_quality:
                continue
            if chosen_status != "Any":
                is_installed = voice_filename(v) in installed
                if chosen_status == "Installed" and not is_installed:
                    continue
                if chosen_status == "Not installed" and is_installed:
                    continue
            if query:
                hay = f"{v['id']} {v['name']} {v['label']}".lower()
                if query not in hay:
                    continue
            self._build_row(v, installed)
            rows += 1

        if rows == 0:
            self._rows_layout.addWidget(hint_label(
                "No voices match. Clear the filter to see everything."))
        self._rows_layout.addStretch(1)

    def _build_row(self, v: PiperVoice, installed: set[str]) -> None:
        self._voice_by_id[v["id"]] = v
        card, lay = make_card()
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)

        left = QVBoxLayout()
        name = card_label(v["label"])
        name.setStyleSheet('font-family:"Segoe UI Semibold"; font-weight:600;')
        left.addWidget(name)
        left.addWidget(hint_label(f"id: {v['id']}   ·   {v['quality']}"))
        row.addLayout(left, 1)

        status = hint_label("")
        self.row_status[v["id"]] = status
        row.addWidget(status)
        row.addSpacing(10)

        if voice_filename(v) in installed:
            status.setText("✓ installed")
            btn = danger_button("Remove", lambda vv=v: self._remove(vv))
        else:
            btn = button("Install", lambda vv=v: self._download(vv))
        self.row_buttons[v["id"]] = btn
        row.addWidget(btn)
        lay.addLayout(row)
        self._rows_layout.addWidget(card)

    # ----- install / remove (reuses pippal.ui.voice_manager backend) -----

    def _download(self, v: PiperVoice) -> None:
        self.row_status[v["id"]].setText("downloading…")
        btn = self.row_buttons.get(v["id"])
        if btn is not None:
            btn.setEnabled(False)
        threading.Thread(
            target=self._download_thread, args=(v,), daemon=True).start()

    def _download_thread(self, v: PiperVoice) -> None:
        try:
            install_piper_voice(v)
            self._install_done.emit(v["id"], True, "")
        except Exception as e:
            self._install_done.emit(v["id"], False, str(e))

    def _on_install_done(self, voice_id: str, ok: bool, err: str) -> None:
        v = self._voice_by_id.get(voice_id)
        if v is None:
            return
        status = self.row_status.get(voice_id)
        btn = self.row_buttons.get(voice_id)
        if ok:
            if status is not None:
                status.setText("✓ installed")
            if btn is not None:
                btn.setEnabled(True)
                btn.setText("Remove")
                btn.setObjectName("Danger")
                btn.style().unpolish(btn)
                btn.style().polish(btn)
                try:
                    btn.clicked.disconnect()
                except Exception:
                    pass
                btn.clicked.connect(lambda _=False, vv=v: self._remove(vv))
            try:
                self.on_changed()
            except Exception as exc:
                import sys
                print(f"[voice_manager_qt] on_changed failed: {exc}",
                      file=sys.stderr)
            if self.on_installed is not None:
                try:
                    self.on_installed(voice_filename(v))
                except Exception as exc:
                    import sys
                    print(f"[voice_manager_qt] on_installed failed: {exc}",
                          file=sys.stderr)
        else:
            if status is not None:
                status.setText("failed")
            if btn is not None:
                btn.setEnabled(True)
            QMessageBox.critical(self, "Download failed", err)

    def _remove(self, v: PiperVoice) -> None:
        ok = QMessageBox.question(
            self, "Remove voice", f"Remove {v['label']}?",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if ok != QMessageBox.Yes:
            return
        for f in (VOICES_DIR / f"{v['id']}.onnx",
                  VOICES_DIR / f"{v['id']}.onnx.json"):
            try:
                f.unlink(missing_ok=True)
            except Exception:
                pass
        try:
            self.on_changed()
        except Exception as exc:
            import sys
            print(f"[voice_manager_qt] on_changed failed: {exc}",
                  file=sys.stderr)
        status = self.row_status.get(v["id"])
        if status is not None:
            status.setText("—")
        btn = self.row_buttons.get(v["id"])
        if btn is not None:
            btn.setText("Install")
            btn.setObjectName("")
            btn.style().unpolish(btn)
            btn.style().polish(btn)
            try:
                btn.clicked.disconnect()
            except Exception:
                pass
            btn.clicked.connect(lambda _=False, vv=v: self._download(vv))
