"""PySide6 Settings window — the 7-card dark form.

Behavioural parity target: ``pippal.ui.settings_window.SettingsWindow``
+ ``pippal.ui.settings_cards``. Same config keys, same Save/Apply/
Reset/Cancel semantics, same Piper voice-combo population, same
hotkey-rebind-on-change, same context-menu install/remove, same
About links. The backend (config/voices/context_menu/plugins) is
reused unchanged; this module only swaps Tk widgets for Qt.

The form keeps a ``self.vars`` dict mapping config keys to small
getter/setter shims so the E2E suite and the command surface can read
and drive values exactly like the Tk window's ``tk.Variable`` map."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QHBoxLayout,
    QLineEdit,
    QMessageBox,
    QScrollArea,
    QSlider,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from .. import __version__, plugins
from ..config import _layered_defaults
from ..context_menu import (
    context_menu_status,
    install_context_menu,
    uninstall_context_menu,
)
from ..voices import installed_voices
from .theme_qt import UI, apply_native_frame
from .voice_manager_qt import QtVoiceManagerDialog
from .widgets_qt import (
    button,
    card_label,
    danger_button,
    hint_label,
    labeled_row,
    link_label,
    make_card,
    primary_button,
    separator,
)


class _Var:
    """Tk-``Variable``-shaped shim over a Qt widget.

    The Tk window exposes ``self.vars[key].get()/.set()``; the E2E
    harness and command server lean on that. Reproducing the same
    surface here keeps the migration honest — tests assert against the
    same keys/types."""

    def __init__(self, getter: Callable[[], Any], setter: Callable[[Any], None]) -> None:
        self._get = getter
        self._set = setter

    def get(self) -> Any:
        return self._get()

    def set(self, value: Any) -> None:
        self._set(value)


class QtSettingsWindow(QWidget):
    """Settings window. Constructed once, shown/hidden on demand —
    same lifecycle contract as the Tk ``SettingsWindow.open()``."""

    closed = Signal()

    def __init__(
        self,
        config: dict[str, Any],
        on_save: Callable[[dict[str, Any]], None],
        on_hotkey_change: Callable[[], list[tuple[str, str, str]] | None],
        on_engine_change: Callable[[], None] | None = None,
    ) -> None:
        super().__init__()
        self.config = config
        self.on_save = on_save
        self.on_hotkey_change = on_hotkey_change
        self.on_engine_change = on_engine_change
        self.vars: dict[str, _Var] = {}
        self._voice_manager: QtVoiceManagerDialog | None = None
        # Widget handles the engine-change handler needs.
        self.engine_combo: QComboBox | None = None
        self.voice_combo: QComboBox | None = None
        self.manage_btn = None
        self.engine_hint = None
        self.speed_label = None
        self.var_label = None
        self.ctx_status = None

        self.setWindowTitle(str(self.config.get("brand_name", "PipPal")))
        self.resize(600, 720)
        self.setMinimumSize(560, 600)
        self._build()

    # ------------------------------------------------------------------
    # Open / close
    # ------------------------------------------------------------------

    def open(self) -> None:
        if not self.isVisible():
            self.show()
        self.raise_()
        self.activateWindow()
        apply_native_frame(self)

    def closeEvent(self, event: Any) -> None:
        self.closed.emit()
        super().closeEvent(event)

    def keyPressEvent(self, event: Any) -> None:
        if event.key() == Qt.Key_Escape:
            self.close()
            return
        super().keyPressEvent(event)

    # ------------------------------------------------------------------
    # Construction
    # ------------------------------------------------------------------

    def _build(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        body = QWidget()
        self._body_layout = QVBoxLayout(body)
        self._body_layout.setContentsMargins(20, 20, 20, 8)
        self._body_layout.setSpacing(12)
        scroll.setWidget(body)
        root.addWidget(scroll, 1)

        # Cards, in the same order the Tk Zone constants produce:
        # Voice / Speech / Hotkeys / Panel / Integration / Notices /
        # About.
        self._build_voice_card()
        self._build_speech_card()
        self._build_hotkeys_card()
        self._build_panel_card()
        self._build_integration_card()
        self._build_notices_card()
        self._build_about_card()
        self._body_layout.addStretch(1)

        root.addWidget(separator())
        root.addLayout(self._build_footer())

    # ----- Voice card -----
    def _build_voice_card(self) -> None:
        card, lay = make_card("Voice")

        self.engine_combo = QComboBox()
        available_engines = sorted(plugins.engines().keys()) or ["piper"]
        self.engine_combo.addItems(available_engines)
        saved_engine = (self.config.get("engine") or "piper").lower()
        if saved_engine in available_engines:
            self.engine_combo.setCurrentText(saved_engine)
        self.engine_combo.currentTextChanged.connect(
            lambda _t: self._on_engine_change())
        self.vars["engine"] = _Var(
            self.engine_combo.currentText,
            lambda v: self.engine_combo.setCurrentText(str(v)),
        )
        lay.addWidget(labeled_row("Engine", self.engine_combo))
        lay.addSpacing(10)

        voice_row = QWidget()
        voice_row.setStyleSheet("background: transparent;")
        vh = QHBoxLayout(voice_row)
        vh.setContentsMargins(0, 0, 0, 0)
        vh.setSpacing(8)
        vlbl = card_label("Voice")
        vlbl.setFixedWidth(110)
        vh.addWidget(vlbl)
        self.voice_combo = QComboBox()
        vh.addWidget(self.voice_combo, 1)
        self.manage_btn = button("Manage…", self._open_voice_manager)
        vh.addWidget(self.manage_btn)
        lay.addWidget(voice_row)

        self.vars["voice_display"] = _Var(
            self.voice_combo.currentText,
            lambda v: self.voice_combo.setCurrentText(str(v)),
        )
        self.vars["voice"] = _Var(
            lambda: self._voice_value,
            lambda v: setattr(self, "_voice_value", str(v)),
        )
        self._voice_value = str(
            self.config.get("voice", _layered_defaults().get("voice", "")))

        lay.addSpacing(8)
        self.engine_hint = hint_label("")
        lay.addWidget(self.engine_hint)

        self._body_layout.addWidget(card)
        self._on_engine_change()

    def _on_engine_change(self) -> None:
        """Re-populate the Voice combo for the selected engine — same
        Piper-install logic the Tk card runs (installed .onnx list,
        Manage/Install call-to-action, disabled placeholder when
        empty)."""
        installed = installed_voices()
        self.voice_combo.blockSignals(True)
        self.voice_combo.clear()
        if installed:
            self.voice_combo.addItems(installed)
            self.voice_combo.setEnabled(True)
            cur = str(self.vars["voice"].get())
            self.voice_combo.setCurrentText(cur if cur in installed else installed[0])
            self.engine_hint.setText(
                "Piper voice. Click Manage to install more from the "
                "curated list.")
            self.manage_btn.setText("Manage…")
        else:
            self.voice_combo.addItem("(no voice installed)")
            self.voice_combo.setEnabled(False)
            self.engine_hint.setText(
                "No Piper voice installed yet. Click Install voices "
                "to download one.")
            self.manage_btn.setText("Install voices…")
        self.voice_combo.blockSignals(False)

    # ----- Speech card -----
    def _build_speech_card(self) -> None:
        card, lay = make_card("Speech")

        ls = float(self.config.get("length_scale", 1.0))
        self._speed = round(1.0 / ls, 2) if ls else 1.0
        speed_slider = QSlider(Qt.Horizontal)
        speed_slider.setMinimum(60)
        speed_slider.setMaximum(170)
        speed_slider.setValue(round(self._speed * 100))
        self.speed_label = card_label("")
        self.speed_label.setFixedWidth(56)
        self.speed_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)

        def _speed_changed(v: int) -> None:
            self._speed = v / 100.0
            self._update_speed_label()

        speed_slider.valueChanged.connect(_speed_changed)
        self.vars["speed"] = _Var(
            lambda: round(self._speed, 2),
            lambda v: speed_slider.setValue(round(float(v) * 100)),
        )
        srow = QWidget()
        srow.setStyleSheet("background: transparent;")
        sh = QHBoxLayout(srow)
        sh.setContentsMargins(0, 0, 0, 0)
        slbl = card_label("Speed")
        slbl.setFixedWidth(110)
        sh.addWidget(slbl)
        sh.addWidget(speed_slider, 1)
        sh.addWidget(self.speed_label)
        lay.addWidget(srow)
        lay.addSpacing(10)
        self._update_speed_label()

        ns = float(self.config.get("noise_scale", 0.667))
        self._noise = ns
        var_slider = QSlider(Qt.Horizontal)
        var_slider.setMinimum(30)
        var_slider.setMaximum(100)
        var_slider.setValue(round(ns * 100))
        self.var_label = card_label("")
        self.var_label.setFixedWidth(56)
        self.var_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)

        def _var_changed(v: int) -> None:
            self._noise = v / 100.0
            self._update_var_label()

        var_slider.valueChanged.connect(_var_changed)
        self.vars["noise_scale"] = _Var(
            lambda: round(self._noise, 3),
            lambda v: var_slider.setValue(round(float(v) * 100)),
        )
        vrow = QWidget()
        vrow.setStyleSheet("background: transparent;")
        vh = QHBoxLayout(vrow)
        vh.setContentsMargins(0, 0, 0, 0)
        vlbl = card_label("Variation")
        vlbl.setFixedWidth(110)
        vh.addWidget(vlbl)
        vh.addWidget(var_slider, 1)
        vh.addWidget(self.var_label)
        lay.addWidget(vrow)
        lay.addSpacing(10)
        self._update_var_label()

        lay.addWidget(hint_label(
            "Speed: 0.6× clearer · 1.0× normal · 1.7× faster.   "
            "Variation: livelier intonation at higher values."))
        self._body_layout.addWidget(card)

    def _update_speed_label(self) -> None:
        self.speed_label.setText(f"{self._speed:.2f}×")

    def _update_var_label(self) -> None:
        self.var_label.setText(f"{self._noise:.2f}")

    # ----- Hotkeys card -----
    def _build_hotkeys_card(self) -> None:
        card, lay = make_card("Hotkeys")
        actions = list(plugins.hotkey_actions())
        for i, (_aid, key, label_text, default) in enumerate(actions):
            if i:
                lay.addSpacing(8)
            edit = QLineEdit(str(self.config.get(key, default)))
            self.vars[key] = _Var(
                edit.text,
                lambda v, e=edit: e.setText(str(v)),
            )
            lay.addWidget(labeled_row(label_text, edit, label_width=150))
        lay.addSpacing(10)
        lay.addWidget(hint_label(
            "Format: windows+shift+r · ctrl+alt+space · alt+shift+f1 …  "
            "Captured combos are suppressed (other apps won't also see "
            "them)."))
        self._body_layout.addWidget(card)

    # ----- Reader panel card -----
    def _build_panel_card(self) -> None:
        card, lay = make_card("Reader panel")
        d = _layered_defaults()

        show_panel = QCheckBox("Show panel while reading")
        show_panel.setChecked(bool(self.config.get("show_overlay", True)))
        self.vars["show_overlay"] = _Var(
            show_panel.isChecked,
            lambda v: show_panel.setChecked(bool(v)),
        )
        lay.addWidget(show_panel)
        lay.addSpacing(4)

        show_text = QCheckBox("Show text with karaoke highlight")
        show_text.setChecked(bool(self.config.get("show_text_in_overlay", True)))
        self.vars["show_text_in_overlay"] = _Var(
            show_text.isChecked,
            lambda v: show_text.setChecked(bool(v)),
        )
        lay.addWidget(show_text)
        lay.addSpacing(12)

        self._spin_row(lay, "Auto-hide delay", "auto_hide_ms",
                       int(d["auto_hide_ms"]), "ms", 300, 8000, 100)
        lay.addSpacing(8)
        self._spin_row(lay, "Distance from taskbar", "overlay_y_offset",
                       int(d["overlay_y_offset"]), "px", 20, 600, 10)
        lay.addSpacing(8)
        self._spin_row(lay, "Karaoke offset", "karaoke_offset_ms",
                       int(d["karaoke_offset_ms"]),
                       "ms (positive = highlight waits, negative = "
                       "highlight leads)", -300, 600, 20)
        self._body_layout.addWidget(card)

    def _spin_row(self, lay: QVBoxLayout, label: str, key: str, default: int,
                  unit: str, lo: int, hi: int, step: int) -> None:
        spin = QSpinBox()
        spin.setRange(lo, hi)
        spin.setSingleStep(step)
        spin.setValue(int(self.config.get(key, default)))
        spin.setFixedWidth(90)
        self.vars[key] = _Var(
            spin.value,
            lambda v, s=spin: s.setValue(int(v)),
        )
        row = QWidget()
        row.setStyleSheet("background: transparent;")
        h = QHBoxLayout(row)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(8)
        lbl = card_label(label)
        lbl.setFixedWidth(150)
        h.addWidget(lbl)
        h.addWidget(spin)
        h.addWidget(hint_label(unit), 1)
        lay.addWidget(row)

    # ----- Windows integration card -----
    def _build_integration_card(self) -> None:
        card, lay = make_card("Windows integration")
        self.ctx_status = card_label("")
        lay.addWidget(self.ctx_status)
        lay.addWidget(hint_label(
            "Adds a 'Read with PipPal' entry to the right-click menu "
            "of .txt and .md files in File Explorer (current user "
            "only)."))
        lay.addSpacing(8)
        row = QWidget()
        row.setStyleSheet("background: transparent;")
        h = QHBoxLayout(row)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(8)
        h.addWidget(button("Install", self._install_ctx))
        h.addWidget(danger_button("Remove", self._remove_ctx))
        h.addStretch(1)
        lay.addWidget(row)
        self._refresh_ctx_status()
        self._body_layout.addWidget(card)

    def _refresh_ctx_status(self) -> None:
        status = context_menu_status()
        if status == "all":
            self.ctx_status.setText(
                "✓ Right-click entry installed for .txt and .md.")
        elif status == "partial":
            self.ctx_status.setText(
                "⚠ Partial install — re-run Install to fix.")
        else:
            self.ctx_status.setText("○ Right-click entry not installed.")

    def _install_ctx(self) -> None:
        try:
            install_context_menu()
        except Exception as e:
            QMessageBox.critical(self, "Install failed", str(e))
            return
        self._refresh_ctx_status()
        QMessageBox.information(
            self, "Installed",
            "Right-click any .txt or .md file in Explorer and choose "
            "'Read with PipPal'. PipPal must be running.")

    def _remove_ctx(self) -> None:
        try:
            uninstall_context_menu()
        except Exception as e:
            QMessageBox.critical(self, "Remove failed", str(e))
            return
        self._refresh_ctx_status()

    # ----- Open-source notices card -----
    def _build_notices_card(self) -> None:
        from .notices_qt import QtNoticesViewer, resolve_notices_path

        card, lay = make_card("Open-source notices")
        lay.addWidget(hint_label(
            "PipPal uses open-source libraries and local TTS runtime "
            "artifacts. Their licences are included with this install "
            "or source checkout."))
        lay.addSpacing(8)
        brand = str(self.config.get("brand_name", "PipPal"))

        def _open() -> None:
            self._notices_viewer = QtNoticesViewer(
                self, resolve_notices_path(), brand)
            self._notices_viewer.show()

        row = QWidget()
        row.setStyleSheet("background: transparent;")
        h = QHBoxLayout(row)
        h.setContentsMargins(0, 0, 0, 0)
        h.addWidget(button("View licences…", _open))
        h.addStretch(1)
        lay.addWidget(row)
        self._body_layout.addWidget(card)

    # ----- About card -----
    def _build_about_card(self) -> None:
        brand = self.config.get("brand_name", "PipPal")
        card, lay = make_card("About")
        title = card_label(f"{brand} {__version__}")
        title.setStyleSheet(
            'font-family:"Segoe UI Semibold"; font-weight:600;'
            f' color:{UI["text"]};')
        lay.addWidget(title)
        lay.addWidget(hint_label("Your little offline reading buddy."))
        lay.addSpacing(8)
        lay.addWidget(hint_label(
            "© 2026 Bug Factory Kft.  ·  Offline-first by design."))
        lay.addSpacing(10)
        link_row = QWidget()
        link_row.setStyleSheet("background: transparent;")
        h = QHBoxLayout(link_row)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(16)
        for text, url in (
            ("Website", "https://pippal.bugfactory.hu"),
            ("GitHub", "https://github.com/bug-factory-kft/pippal"),
            ("Licence (MIT)",
             "https://github.com/bug-factory-kft/pippal/blob/main/LICENSE.md"),
            ("Privacy",
             "https://github.com/bug-factory-kft/pippal/blob/main/docs/PRIVACY.md"),
            ("Terms",
             "https://github.com/bug-factory-kft/pippal/blob/main/docs/TERMS.md"),
        ):
            lbl = link_label(text, url)
            lbl.linkActivated.connect(self._open_url)
            h.addWidget(lbl)
        h.addStretch(1)
        lay.addWidget(link_row)
        self._body_layout.addWidget(card)

    @staticmethod
    def _open_url(url: str) -> None:
        import webbrowser
        webbrowser.open(url)

    # ----- Footer -----
    def _build_footer(self) -> QHBoxLayout:
        footer = QHBoxLayout()
        footer.setContentsMargins(24, 12, 24, 16)
        footer.setSpacing(8)
        self.reset_btn = button("Reset to defaults", self._reset_to_defaults)
        self.cancel_btn = button("Cancel", self.close)
        self.apply_btn = button("Apply", self._apply)
        self.save_btn = primary_button("Save", self._save)
        footer.addWidget(self.reset_btn)
        footer.addStretch(1)
        footer.addWidget(self.cancel_btn)
        footer.addWidget(self.apply_btn)
        footer.addWidget(self.save_btn)
        return footer

    # ------------------------------------------------------------------
    # Voice Manager
    # ------------------------------------------------------------------

    def _open_voice_manager(
        self,
        *,
        on_installed: Callable[[str], None] | None = None,
    ) -> None:
        self._voice_manager = QtVoiceManagerDialog(
            self,
            on_changed=self._on_engine_change,
            on_installed=on_installed,
        )
        self._voice_manager.show()
        self._voice_manager.raise_()
        self._voice_manager.activateWindow()

    # ------------------------------------------------------------------
    # Save / Apply / Reset — same candidate-dict semantics as Tk.
    # ------------------------------------------------------------------

    def _save(self) -> None:
        self._persist(close=True)

    def _apply(self) -> None:
        self._persist(close=False)

    def _reset_to_defaults(self) -> None:
        ok = QMessageBox.question(
            self, "Reset to defaults",
            "Reset every field to its built-in default? Click Apply or "
            "Save afterwards to keep them.",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if ok != QMessageBox.Yes:
            return
        d = _layered_defaults()
        if "length_scale" in d and "speed" in self.vars:
            self.vars["speed"].set(round(1.0 / float(d["length_scale"]), 2))
        skip = {"speed", "voice_display"}
        for key, var in list(self.vars.items()):
            if key in skip or key not in d:
                continue
            try:
                cur = var.get()
            except Exception:
                continue
            try:
                if isinstance(cur, bool):
                    var.set(bool(d[key]))
                elif isinstance(cur, int) and not isinstance(cur, bool):
                    var.set(int(d[key]))
                elif isinstance(cur, float):
                    var.set(float(d[key]))
                else:
                    var.set(str(d[key]))
            except Exception:
                pass
        self._update_speed_label()
        self._update_var_label()
        self._on_engine_change()

    def _persist(self, *, close: bool) -> None:
        candidate = dict(self.config)
        eng = str(self.vars["engine"].get()).lower()
        candidate["engine"] = eng

        for hook in plugins.voice_card_persist_hooks():
            try:
                hook(self, eng, candidate)
            except Exception as exc:
                import sys
                print(f"[settings-qt] persist hook error: {exc}",
                      file=sys.stderr)

        speed = max(0.4, float(self.vars["speed"].get()))
        candidate["length_scale"] = round(1.0 / speed, 3)

        skip = {"engine", "voice", "voice_display", "speed"}
        for key, var in list(self.vars.items()):
            if key in skip:
                continue
            try:
                value = var.get()
            except Exception:
                continue
            if isinstance(value, str):
                value = value.strip()
                if key.startswith("hotkey_"):
                    value = value.lower()
            candidate[key] = value

        try:
            self.on_save(candidate)
        except Exception as e:
            QMessageBox.critical(self, "Save error", str(e))
            return

        _hotkey_keys = [a[1] for a in plugins.hotkey_actions()]
        hotkeys_changed = any(
            self.config.get(k, "") != candidate.get(k, "")
            for k in _hotkey_keys)

        self.config.clear()
        self.config.update(candidate)
        if eng == "piper" and "voice" in candidate:
            self.vars["voice"].set(str(candidate["voice"]))

        if hotkeys_changed:
            try:
                failures = self.on_hotkey_change() or []
            except Exception as e:
                QMessageBox.warning(
                    self, "Hotkey error",
                    f"Could not bind hotkey: {e}\n"
                    "Format example: ctrl+shift+x")
                return
            if failures:
                lines = "\n".join(
                    f"  • {aid} = '{combo}' — {err}"
                    for aid, combo, err in failures)
                QMessageBox.warning(
                    self, "Hotkey error",
                    "Saved, but these hotkeys could not be bound:\n\n"
                    f"{lines}\n\nFormat example: ctrl+shift+x")

        if callable(self.on_engine_change):
            try:
                self.on_engine_change()
            except Exception:
                pass

        if close:
            self.close()
