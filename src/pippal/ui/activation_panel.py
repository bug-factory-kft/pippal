"""First-run activation panel for the Core tray app."""

from __future__ import annotations

import threading
import tkinter as tk
from collections.abc import Callable
from tkinter import messagebox, ttk
from typing import Any

from ..onboarding import (
    READINESS_MISSING_PIPER,
    READINESS_MISSING_VOICE,
    FirstRunReadiness,
    activation_sample_text,
    build_activation_readiness,
    default_piper_voice,
    mark_activation_complete,
)
from .theme import UI, apply_dark_theme, make_card
from .voice_manager import install_piper_voice


class FirstRunActivationPanel:
    def __init__(
        self,
        root: tk.Tk,
        config: dict[str, Any],
        *,
        on_play_sample: Callable[[str], None],
        on_open_settings: Callable[[], None],
        on_open_voice_manager: Callable[[], None],
        on_open_setup: Callable[[], None] | None = None,
    ) -> None:
        self.root = root
        self.config = config
        self.on_play_sample = on_play_sample
        self.on_open_settings = on_open_settings
        self.on_open_voice_manager = on_open_voice_manager
        self.on_open_setup = on_open_setup
        self.win: tk.Toplevel | None = None
        self._frame: ttk.Frame | None = None
        self._status_var = tk.StringVar(master=root, value="")
        self._sample_started = False
        self._installing_default_voice = False

    def open(self) -> None:
        if self.win is not None and self.win.winfo_exists():
            self.win.lift()
            self.win.focus_force()
            return

        self._sample_started = False

        w = tk.Toplevel(self.root)
        self.win = w
        w.title("PipPal - First-run check")
        w.resizable(False, False)
        w.protocol("WM_DELETE_WINDOW", self._close)
        apply_dark_theme(w)

        frame = ttk.Frame(w, style="TFrame", padding=(22, 20, 22, 20))
        frame.pack(fill="both", expand=True)
        self._frame = frame
        self._render()
        self._fit_to_content()
        w.deiconify()
        w.lift()

    def _render(self, status_override: str | None = None) -> FirstRunReadiness:
        readiness = build_activation_readiness(self.config)
        frame = self._frame
        if frame is None:
            return readiness
        for child in frame.winfo_children():
            child.destroy()

        status_text = status_override or readiness.message
        if self._installing_default_voice and readiness.status == READINESS_MISSING_VOICE:
            status_text = (
                "Installing default English voice for offline reading... "
                "Downloading the model and metadata."
            )
        self._status_var.set(status_text)

        ttk.Label(
            frame,
            text="PipPal is ready to read locally",
            style="Title.TLabel",
        ).pack(anchor="w")
        ttk.Label(
            frame,
            text=(
                "PipPal reads selected text aloud on this PC.\n"
                "No account. No telemetry. No cloud TTS.\n"
                "Let's make sure you can hear it now."
            ),
            style="Sub.TLabel",
            justify="left",
        ).pack(anchor="w", pady=(6, 16))

        self._build_readiness_card(frame, readiness)
        self._build_practice_card(frame, readiness)
        self._build_actions(frame, readiness)
        return readiness

    def _fit_to_content(self) -> None:
        if self.win is None or not self.win.winfo_exists():
            return
        self.win.update_idletasks()
        width = max(520, self.win.winfo_reqwidth())
        height = self.win.winfo_reqheight()
        x = max((self.win.winfo_screenwidth() - width) // 2, 0)
        y = max((self.win.winfo_screenheight() - height) // 3, 0)
        self.win.geometry(f"{width}x{height}+{x}+{y}")

    def _build_readiness_card(
        self,
        parent: tk.Misc,
        readiness: FirstRunReadiness,
    ) -> None:
        outer, card = make_card(parent, "Local voice check")
        outer.pack(fill="x", pady=(0, 12))
        rows = (
            readiness.engine_label,
            f"Voice: {readiness.voice_label}",
            f"Hotkey: {readiness.hotkey_label}",
        )
        for row in rows:
            ttk.Label(card, text=row, style="Card.TLabel").pack(anchor="w", pady=(0, 4))
        ttk.Label(
            card,
            textvariable=self._status_var,
            style="CardHint.TLabel",
            wraplength=440,
            justify="left",
        ).pack(anchor="w", pady=(8, 0))

    def _build_practice_card(
        self,
        parent: tk.Misc,
        readiness: FirstRunReadiness,
    ) -> None:
        outer, card = make_card(parent, "Try it in any app")
        outer.pack(fill="x", pady=(0, 12))
        ttk.Label(
            card,
            text="Select text in a browser, PDF, document, or this box.",
            style="Card.TLabel",
            wraplength=440,
            justify="left",
        ).pack(anchor="w", pady=(0, 8))
        sample = activation_sample_text(readiness.hotkey_label)
        text = tk.Text(
            card,
            height=2,
            width=52,
            wrap="word",
            bg=UI["bg_input"],
            fg=UI["text"],
            insertbackground=UI["text"],
            relief="flat",
            padx=8,
            pady=7,
        )
        text.insert("1.0", sample)
        text.pack(fill="x")

    def _build_actions(
        self,
        parent: tk.Misc,
        readiness: FirstRunReadiness,
    ) -> None:
        row = ttk.Frame(parent, style="TFrame")
        row.pack(fill="x")

        if readiness.status == READINESS_MISSING_PIPER:
            ttk.Button(
                row,
                text="Open setup instructions",
                style="Primary.TButton",
                command=self._open_setup,
            ).pack(side="right")
            ttk.Button(row, text="Quit", command=self._close).pack(
                side="right",
                padx=(0, 8),
            )
            return

        if readiness.status == READINESS_MISSING_VOICE:
            install_button = ttk.Button(
                row,
                text="Install default voice",
                style="Primary.TButton",
                command=self._install_default_voice,
            )
            install_button.pack(side="right")
            ttk.Button(
                row,
                text="Open Voice Manager",
                command=self.on_open_voice_manager,
            ).pack(side="right", padx=(0, 8))
            ttk.Button(row, text="Skip for now", command=self._close).pack(
                side="right",
                padx=(0, 8),
            )
            if self._installing_default_voice:
                self._set_buttons_state("disabled")
            return

        ttk.Button(
            row,
            text="Play sample",
            style="Primary.TButton",
            command=lambda: self._play_sample(readiness),
        ).pack(side="right")
        ttk.Button(row, text="Yes, continue", command=self._confirm_sample).pack(
            side="right",
            padx=(0, 8),
        )
        ttk.Button(row, text="Open Settings", command=self.on_open_settings).pack(
            side="right",
            padx=(0, 8),
        )
        ttk.Button(row, text="Skip for now", command=self._close).pack(
            side="left",
        )

    def _set_buttons_state(self, state: str) -> None:
        frame = self._frame
        if frame is None:
            return
        stack = list(frame.winfo_children())
        while stack:
            widget = stack.pop()
            if isinstance(widget, ttk.Button):
                widget.config(state=state)
            stack.extend(widget.winfo_children())

    def _install_default_voice(self) -> None:
        if self._installing_default_voice:
            return
        self._installing_default_voice = True
        self._sample_started = False
        self._status_var.set(
            "Installing default English voice for offline reading... "
            "Downloading the model and metadata."
        )
        self._set_buttons_state("disabled")
        threading.Thread(target=self._install_default_voice_thread, daemon=True).start()

    def _install_default_voice_thread(self) -> None:
        try:
            installed_filename = install_piper_voice(default_piper_voice())
        except Exception as exc:
            err_msg = str(exc) or exc.__class__.__name__
            self.root.after(
                0,
                lambda msg=err_msg: self._finish_default_voice_install(error=msg),
            )
        else:
            self.root.after(
                0,
                lambda filename=installed_filename: self._finish_default_voice_install(
                    installed_filename=filename,
                ),
            )

    def _finish_default_voice_install(
        self,
        *,
        installed_filename: str | None = None,
        error: str | None = None,
    ) -> None:
        self._installing_default_voice = False
        if self.win is None or not self.win.winfo_exists():
            return
        if error is not None:
            status = (
                "The voice download did not finish. Check your connection or "
                "choose a voice later in Voice Manager."
            )
            self._status_var.set(status)
            self._set_buttons_state("normal")
            messagebox.showerror("Voice install failed", f"{status}\n\n{error}", parent=self.win)
            return

        if installed_filename is not None:
            self.config["voice"] = installed_filename
        self._sample_started = False
        self._render(
            "Default English voice installed for offline reading. "
            "Play the sample to finish activation."
        )
        self._fit_to_content()

    def _play_sample(self, readiness: FirstRunReadiness) -> None:
        if not readiness.can_play_sample:
            self._status_var.set(readiness.message)
            return
        self._sample_started = True
        self._status_var.set("Playing sample...")
        self.on_play_sample(activation_sample_text(readiness.hotkey_label))

    def _confirm_sample(self) -> None:
        if not self._sample_started:
            self._status_var.set("Play the sample first, then confirm you heard it.")
            return
        mark_activation_complete("sample")
        self._status_var.set("Done. PipPal can read selected text on this PC.")

    def _open_setup(self) -> None:
        if self.on_open_setup is not None:
            self.on_open_setup()
        self._status_var.set("Run setup.ps1 from this checkout, then open PipPal again.")

    def _close(self) -> None:
        if self.win is not None and self.win.winfo_exists():
            self.win.destroy()
        self.win = None
        self._frame = None
