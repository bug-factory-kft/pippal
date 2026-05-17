"""PySide6 first-run activation panel.

Parity target: ``pippal.ui.activation_panel.FirstRunActivationPanel``.
Same readiness states (missing piper / missing voice / ready), same
"Local voice check" + "Try it in any app" cards, same action buttons
(Skip / Open Settings / Open Voice Manager / Install default voice /
Play sample / Finish setup / Close), same state-poll that flips the
status line. All onboarding/readiness logic is reused from
``pippal.onboarding`` unchanged; default-voice install reuses
``pippal.ui.voice_manager.install_piper_voice``."""

from __future__ import annotations

import threading
from collections.abc import Callable
from typing import Any

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QMessageBox,
    QPlainTextEdit,
    QVBoxLayout,
    QWidget,
)

from ..onboarding import (
    READINESS_MISSING_PIPER,
    READINESS_MISSING_VOICE,
    READINESS_READY,
    FirstRunReadiness,
    activation_failure_recovery_message,
    activation_sample_text,
    build_activation_readiness,
    default_piper_voice,
    load_activation_state,
    mark_activation_complete,
)
from ..ui.voice_manager import install_piper_voice
from .theme_qt import apply_native_frame
from .widgets_qt import (
    button,
    card_label,
    hint_label,
    make_card,
    primary_button,
    sub_label,
    title_label,
)


class QtActivationPanel(QWidget):

    _voice_install_done = Signal(object, object)  # installed_filename, error

    def __init__(
        self,
        config: dict[str, Any],
        *,
        on_play_sample: Callable[[str], None],
        on_open_settings: Callable[[], None],
        on_open_voice_manager: Callable[[], None],
        on_open_setup: Callable[[], None] | None = None,
    ) -> None:
        super().__init__(None, Qt.Window)
        self.config = config
        self.on_play_sample = on_play_sample
        self.on_open_settings = on_open_settings
        self.on_open_voice_manager = on_open_voice_manager
        self.on_open_setup = on_open_setup

        self._status_text = ""
        self._sample_started = False
        self._installing_default_voice = False

        self.setWindowTitle(str(self.config.get("brand_name", "PipPal")))
        self.resize(520, 420)

        self._root = QVBoxLayout(self)
        self._root.setContentsMargins(22, 20, 22, 20)
        self._root.setSpacing(0)

        self._voice_install_done.connect(self._finish_default_voice_install)

        self._poll = QTimer(self)
        self._poll.setInterval(750)
        self._poll.timeout.connect(self._refresh_activation_state)

        self._render()

    def open(self) -> None:
        if not self.isVisible():
            self.show()
        self.raise_()
        self.activateWindow()
        if not self._poll.isActive():
            self._poll.start()
        apply_native_frame(self)

    def closeEvent(self, event: Any) -> None:
        self._poll.stop()
        super().closeEvent(event)

    def keyPressEvent(self, event: Any) -> None:
        if event.key() == Qt.Key_Escape:
            self.close()
            return
        super().keyPressEvent(event)

    # ------------------------------------------------------------------

    def _clear(self) -> None:
        while self._root.count():
            item = self._root.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()
            else:
                lay = item.layout()
                if lay is not None:
                    while lay.count():
                        sub = lay.takeAt(0)
                        sw = sub.widget()
                        if sw is not None:
                            sw.deleteLater()

    def _render(self, status_override: str | None = None) -> FirstRunReadiness:
        readiness = build_activation_readiness(self.config)
        self._clear()

        status_text = status_override or readiness.message
        if status_override is None and readiness.status == READINESS_READY:
            state = load_activation_state()
            if state.is_complete:
                status_text = "Done. PipPal can read selected text on this PC."
            else:
                recovery = activation_failure_recovery_message(
                    state.last_failure, readiness.hotkey_label)
                status_text = recovery or status_text
        if self._installing_default_voice and \
                readiness.status == READINESS_MISSING_VOICE:
            status_text = (
                "Installing default English voice for offline reading... "
                "Downloading the model and metadata.")
        self._status_text = status_text

        if readiness.status == READINESS_MISSING_PIPER:
            title = "PipPal needs a local reading engine"
            subtitle = ("The tray app is running so you can repair setup "
                        "or switch engines.")
        elif readiness.status == READINESS_MISSING_VOICE:
            title = "PipPal needs a local voice"
            subtitle = ("Install an offline voice before the first reading "
                        "test.\nNo account. No telemetry. No cloud TTS.")
        else:
            title = "PipPal is ready to read locally"
            subtitle = ("PipPal reads selected text aloud on this PC.\n"
                        "No account. No telemetry. No cloud TTS.\n"
                        "Let's make sure you can hear it now.")

        self._root.addWidget(title_label(title))
        self._root.addWidget(sub_label(subtitle))
        self._root.addSpacing(16)
        self._build_readiness_card(readiness)
        self._root.addSpacing(12)
        self._build_practice_card(readiness)
        self._root.addSpacing(12)
        self._build_actions(readiness)
        self._root.addStretch(1)
        return readiness

    def _build_readiness_card(self, readiness: FirstRunReadiness) -> None:
        card, lay = make_card("Local voice check")
        for row in (readiness.engine_label,
                    f"Voice: {readiness.voice_label}",
                    f"Hotkey: {readiness.hotkey_label}"):
            lay.addWidget(card_label(row))
            lay.addSpacing(4)
        self._status_label = hint_label(self._status_text)
        lay.addSpacing(4)
        lay.addWidget(self._status_label)
        self._root.addWidget(card)

    def _build_practice_card(self, readiness: FirstRunReadiness) -> None:
        card, lay = make_card("Try it in any app")
        lay.addWidget(card_label(
            "Select text in a browser, PDF, document, or this box."))
        lay.addSpacing(8)
        box = QPlainTextEdit()
        box.setPlainText(activation_sample_text(readiness.hotkey_label))
        box.setFixedHeight(58)
        lay.addWidget(box)
        self._root.addWidget(card)

    def _build_actions(self, readiness: FirstRunReadiness) -> None:
        row = QHBoxLayout()
        row.setSpacing(8)

        if readiness.status == READINESS_MISSING_PIPER:
            row.addWidget(button("Close", self.close))
            row.addStretch(1)
            row.addWidget(button("Open Settings", self.on_open_settings))
            row.addWidget(primary_button("Open setup instructions",
                                         self._open_setup))
            self._root.addLayout(row)
            return

        if readiness.status == READINESS_MISSING_VOICE:
            self._skip_btn = button("Skip for now", self.close)
            self._ovm_btn = button("Open Voice Manager",
                                    self.on_open_voice_manager)
            self._install_btn = primary_button("Install default voice",
                                                self._install_default_voice)
            row.addWidget(self._skip_btn)
            row.addStretch(1)
            row.addWidget(self._ovm_btn)
            row.addWidget(self._install_btn)
            if self._installing_default_voice:
                for b in (self._skip_btn, self._ovm_btn, self._install_btn):
                    b.setEnabled(False)
            self._root.addLayout(row)
            return

        if load_activation_state().is_complete:
            row.addWidget(button(
                "Play sample again",
                lambda: self._play_sample(readiness)))
            row.addStretch(1)
            row.addWidget(button("Open Settings", self.on_open_settings))
            row.addWidget(primary_button("Close", self.close))
            self._root.addLayout(row)
            return

        play_label = ("Play sample again" if self._sample_started
                      else "Play sample")
        play_btn = (button if self._sample_started else primary_button)(
            play_label, lambda: self._play_sample(readiness))
        finish_btn = (primary_button if self._sample_started else button)(
            "Finish setup", self._confirm_sample)
        self._confirm_button = finish_btn
        if not self._sample_started:
            finish_btn.setEnabled(False)

        row.addWidget(button("Skip for now", self.close))
        row.addStretch(1)
        row.addWidget(button("Open Settings", self.on_open_settings))
        row.addWidget(finish_btn)
        row.addWidget(play_btn)
        self._root.addLayout(row)

    # ------------------------------------------------------------------

    def _set_status(self, text: str) -> None:
        self._status_text = text
        if getattr(self, "_status_label", None) is not None:
            self._status_label.setText(text)

    def _refresh_activation_state(self) -> None:
        readiness = build_activation_readiness(self.config)
        if self._installing_default_voice and \
                readiness.status == READINESS_MISSING_VOICE:
            self._set_status(
                "Installing default English voice for offline reading... "
                "Downloading the model and metadata.")
            return
        if readiness.status == READINESS_READY:
            state = load_activation_state()
            if state.is_complete:
                self._set_status(
                    "Done. PipPal can read selected text on this PC.")
            else:
                recovery = activation_failure_recovery_message(
                    state.last_failure, readiness.hotkey_label)
                if recovery is not None:
                    self._set_status(recovery)

    def _install_default_voice(self) -> None:
        if self._installing_default_voice:
            return
        self._installing_default_voice = True
        self._sample_started = False
        self._set_status(
            "Installing default English voice for offline reading... "
            "Downloading the model and metadata.")
        for attr in ("_skip_btn", "_ovm_btn", "_install_btn"):
            b = getattr(self, attr, None)
            if b is not None:
                b.setEnabled(False)
        threading.Thread(
            target=self._install_default_voice_thread, daemon=True).start()

    def _install_default_voice_thread(self) -> None:
        try:
            installed = install_piper_voice(default_piper_voice())
        except Exception as exc:
            self._voice_install_done.emit(
                None, str(exc) or exc.__class__.__name__)
        else:
            self._voice_install_done.emit(installed, None)

    def _finish_default_voice_install(
        self, installed_filename: Any, error: Any,
    ) -> None:
        self._installing_default_voice = False
        if error is not None:
            status = ("The voice download did not finish. Check your "
                      "connection or choose a voice later in Voice "
                      "Manager.")
            self._set_status(status)
            self._render(status)
            QMessageBox.critical(
                self, "Voice install failed", f"{status}\n\n{error}")
            return
        if installed_filename is not None:
            self.config["voice"] = installed_filename
        self._sample_started = False
        self._render(
            "Default English voice installed for offline reading. "
            "Play the sample to finish activation.")

    def apply_installed_voice(self, installed_filename: str) -> None:
        self.config["voice"] = installed_filename
        self._sample_started = False
        self._render(
            "Voice installed from Voice Manager. "
            "Play the sample to finish activation.")

    def _play_sample(self, readiness: FirstRunReadiness) -> None:
        if not readiness.can_play_sample:
            self._set_status(readiness.message)
            return
        self._sample_started = True
        if load_activation_state().is_complete:
            status = "Playing sample again. PipPal is already set up."
        else:
            status = "Playing sample. If you can hear it, finish setup."
        self._render(status)
        self.on_play_sample(activation_sample_text(readiness.hotkey_label))

    def _confirm_sample(self) -> None:
        if not self._sample_started:
            self._set_status(
                "Play the sample first, then confirm you heard it.")
            return
        mark_activation_complete("sample")
        self._set_status("Done. PipPal can read selected text on this PC.")
        QTimer.singleShot(900, self.close)

    def _open_setup(self) -> None:
        if self.on_open_setup is not None:
            self.on_open_setup()
        self._set_status(
            "Run setup.ps1 from this checkout, then use First-run check "
            "again.")
