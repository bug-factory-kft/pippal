"""The Settings window — dark, card-based, with engine / voice / hotkey
/ AI / panel / Windows-integration sections."""

from __future__ import annotations

import threading
import tkinter as tk
from collections.abc import Callable
from tkinter import messagebox, ttk
from typing import Any

from .. import plugins
from ..config import DEFAULT_CONFIG
from ..context_menu import (
    context_menu_status,
    install_context_menu,
    uninstall_context_menu,
)
from ..ollama_client import OllamaClient
from ..voices import KOKORO_CURATED, installed_voices
from .theme import UI, apply_dark_theme
from .voice_manager import VoiceManagerDialog


# Pro-only behaviour that the Settings window touches when the user
# picks the Kokoro engine. The Free distribution doesn't ship these
# modules; if pippal_pro isn't installed the engine combo never offers
# 'kokoro' as an option (plugins.engines() doesn't include it), so
# the lazy lookups below are unreachable in a Free-only build.
def _pro_kokoro_helpers() -> tuple[Any | None, Any | None]:
    """Return (kokoro_installed_fn, KokoroInstallDialog_cls) or (None, None)
    when pippal_pro isn't loaded. Localised here so the Settings UI
    only has one bridge point to the Pro package."""
    try:
        from pippal_pro.moods import kokoro_installed
        from pippal_pro.ui.kokoro_install import KokoroInstallDialog
    except ImportError:
        return None, None
    return kokoro_installed, KokoroInstallDialog


class SettingsWindow:
    def __init__(
        self,
        root: tk.Misc,
        config: dict[str, Any],
        on_save: Callable[[dict[str, Any]], None],
        on_hotkey_change: Callable[[], list[tuple[str, str, str]] | None],
        on_engine_change: Callable[[], None] | None = None,
    ) -> None:
        self.root = root
        self.config = config
        self.on_save = on_save
        self.on_hotkey_change = on_hotkey_change
        self.on_engine_change = on_engine_change
        self.win: tk.Toplevel | None = None
        self.vars: dict[str, tk.Variable] = {}

    # ------------------------------------------------------------------
    # Open / close
    # ------------------------------------------------------------------

    def open(self) -> None:
        if self.win is not None and self.win.winfo_exists():
            self.win.lift()
            self.win.focus_force()
            return

        w = tk.Toplevel(self.root)
        self.win = w
        w.title(self.config.get("brand_name", "PipPal"))
        w.geometry("600x700")
        w.minsize(560, 600)

        apply_dark_theme(w)
        self._build_header(w)
        body = self._build_scrollable_body(w)
        # Cards are registered into the plugin host (pippal.plugins) by
        # whichever package supplies them — the Free pippal package
        # registers Voice/Speech/Hotkeys/Panel/Integration/About via
        # `_register_free.py`; pippal_pro adds the AI card. The order
        # comes from each registration's `zone` (with `order` as a
        # tie-breaker).
        for builder in plugins.settings_cards():
            builder(self, body)
        self._build_footer(w)

        w.protocol("WM_DELETE_WINDOW", self._close)

    def _close(self) -> None:
        if self.win is not None:
            try:
                self.win.destroy()
            except Exception:
                pass
            self.win = None

    # ------------------------------------------------------------------
    # UI construction helpers
    # ------------------------------------------------------------------

    def _build_header(self, w: tk.Toplevel) -> None:
        brand = self.config.get("brand_name", "PipPal")
        header = ttk.Frame(w, style="Header.TFrame", padding=(24, 18, 24, 14))
        header.pack(fill="x")
        title_row = ttk.Frame(header, style="Header.TFrame")
        title_row.pack(fill="x")
        dot = tk.Canvas(title_row, width=14, height=14, bg=UI["bg"], highlightthickness=0)
        dot.create_oval(2, 2, 12, 12, fill=UI["accent"], outline="")
        dot.pack(side="left", padx=(0, 10))
        ttk.Label(title_row, text=brand, style="Title.TLabel").pack(side="left")
        ttk.Label(header, text="Settings", style="Sub.TLabel").pack(anchor="w", pady=(2, 0))

    def _build_scrollable_body(self, w: tk.Toplevel) -> ttk.Frame:
        body_outer = ttk.Frame(w, style="TFrame")
        body_outer.pack(fill="both", expand=True, padx=20)
        canvas = tk.Canvas(body_outer, bg=UI["bg"], highlightthickness=0)
        canvas.pack(side="left", fill="both", expand=True)
        sb = ttk.Scrollbar(body_outer, orient="vertical", command=canvas.yview,
                           style="Vertical.TScrollbar")
        sb.pack(side="right", fill="y")
        canvas.configure(yscrollcommand=sb.set)

        body = ttk.Frame(canvas, style="TFrame")
        body_id = canvas.create_window((0, 0), window=body, anchor="nw")

        def _resize(e: tk.Event) -> None:
            canvas.configure(scrollregion=canvas.bbox("all"))
            canvas.itemconfig(body_id, width=e.width)
        canvas.bind("<Configure>", _resize)
        body.bind("<Configure>",
                  lambda _e: canvas.configure(scrollregion=canvas.bbox("all")))
        # Bind to the canvas itself, NOT bind_all — `bind_all` registers
        # a global handler that survives the window and hijacks scroll
        # for the rest of the app.
        canvas.bind("<MouseWheel>",
                    lambda e: canvas.yview_scroll(int(-e.delta / 120), "units"))
        return body

    def _build_footer(self, w: tk.Toplevel) -> None:
        footer = ttk.Frame(w, style="Header.TFrame", padding=(24, 12, 24, 16))
        footer.pack(fill="x", side="bottom")
        sep = tk.Frame(w, bg=UI["border"], height=1)
        sep.pack(fill="x", side="bottom", before=footer)
        # Reset on the left, action buttons on the right — Windows
        # Control Panel-style. Save (Primary) is the rightmost so the
        # Enter key picks it up by visual convention.
        ttk.Button(footer, text="Reset to defaults",
                   command=self._reset_to_defaults).pack(side="left")
        ttk.Button(footer, text="Save", style="Primary.TButton",
                   command=self._save).pack(side="right")
        ttk.Button(footer, text="Apply",
                   command=self._apply).pack(side="right", padx=(0, 8))
        ttk.Button(footer, text="Cancel",
                   command=self._close).pack(side="right", padx=(0, 8))

    # ------------------------------------------------------------------
    # Live UI updates
    # ------------------------------------------------------------------

    def _update_speed_label(self) -> None:
        v = float(self.vars["speed"].get())
        self.speed_label.config(text=f"{v:.2f}×")

    def _update_var_label(self) -> None:
        v = float(self.vars["noise_scale"].get())
        self.var_label.config(text=f"{v:.2f}")

    def _refresh_voice_list(self) -> None:
        if "engine" in self.vars and self.vars["engine"].get() == "piper":
            self._on_engine_change()

    def _on_engine_change(self) -> None:
        eng = self.vars["engine"].get()
        if eng == "kokoro":
            labels = [f"{vid} — {desc}" for vid, desc in KOKORO_CURATED]
            self.voice_combo["values"] = labels
            cur = str(self.vars["kokoro_voice"].get() or "af_bella")
            match = next((lab for lab in labels if lab.startswith(cur + " —")), labels[0])
            self.vars["voice_display"].set(match)
            kokoro_installed, _dlg = _pro_kokoro_helpers()
            if kokoro_installed is None:
                # Pro not loaded — shouldn't happen because the engine
                # combo wouldn't even have offered 'kokoro', but degrade
                # gracefully if the user typed it manually into config.
                self.engine_hint.config(
                    text="Kokoro engine requires PipPal Pro.")
                self.kokoro_install_btn.pack_forget()
                self.manage_btn.pack_forget()
            elif kokoro_installed():
                self.engine_hint.config(
                    text="Kokoro is installed. Voices are bundled — no per-voice download.")
                self.kokoro_install_btn.pack_forget()
                self.manage_btn.pack_forget()
            else:
                self.engine_hint.config(
                    text="Kokoro is not installed yet. The model and voices "
                         "(~340 MB) need to be downloaded once.")
                self.kokoro_install_btn.pack(anchor="w", pady=(8, 0))
                self.manage_btn.pack_forget()
        else:
            installed = installed_voices() or [DEFAULT_CONFIG["voice"]]
            self.voice_combo["values"] = installed
            cur = str(self.vars["voice"].get())
            self.vars["voice_display"].set(cur if cur in installed else installed[0])
            self.engine_hint.config(
                text="Piper voice. Click Manage to install more from the curated list.")
            self.kokoro_install_btn.pack_forget()
            self.manage_btn.pack(side="left", padx=(10, 0))

    def _install_kokoro(self) -> None:
        _, KokoroInstallDialog = _pro_kokoro_helpers()
        if KokoroInstallDialog is not None:
            KokoroInstallDialog(self.win, on_done=self._on_engine_change)

    def _refresh_ctx_status(self) -> None:
        status = context_menu_status()
        if status == "all":
            self.ctx_status.config(text="✓ Right-click entry installed for .txt and .md.")
        elif status == "partial":
            self.ctx_status.config(
                text="⚠ Partial install — re-run Install to fix.")
        else:
            self.ctx_status.config(text="○ Right-click entry not installed.")

    def _install_ctx(self) -> None:
        try:
            install_context_menu()
        except Exception as e:
            messagebox.showerror("Install failed", str(e), parent=self.win)
            return
        self._refresh_ctx_status()
        messagebox.showinfo(
            "Installed",
            "Right-click any .txt or .md file in Explorer and choose "
            "'Read with PipPal'. PipPal must be running.",
            parent=self.win,
        )

    def _remove_ctx(self) -> None:
        try:
            uninstall_context_menu()
        except Exception as e:
            messagebox.showerror("Remove failed", str(e), parent=self.win)
            return
        self._refresh_ctx_status()

    def _refresh_ollama_models(self, quiet: bool = False) -> None:
        """List Ollama models in a background thread so the Settings UI
        doesn't freeze for 3 s when Ollama is down."""
        endpoint = self.vars.get("ollama_endpoint")
        url = endpoint.get() if endpoint else DEFAULT_CONFIG["ollama_endpoint"]

        def _fetch() -> None:
            client = OllamaClient(url)
            available = client.is_available()
            models = client.list_models() if available else []
            try:
                self.win.after(
                    0,
                    lambda: self._apply_ollama_models(models, available, quiet, url),
                )
            except Exception:
                pass

        threading.Thread(target=_fetch, daemon=True).start()

    def _apply_ollama_models(
        self,
        models: list[str],
        available: bool,
        quiet: bool,
        url: str,
    ) -> None:
        if self.win is None or not self.win.winfo_exists():
            return
        if not available:
            # Ollama daemon not reachable. Disable the model picker and
            # surface the install hint inline (no popup — the label is
            # less obtrusive and stays visible while the user reads).
            self.ollama_status_label.config(
                text="○ Ollama not detected. Install from https://ollama.com — "
                     "AI hotkeys (Summary / Explain / Translate / Define) will "
                     "speak an install hint until it's running.",
            )
            self.model_combo["values"] = []
            self.model_combo.config(state="disabled")
            return
        # Reachable — re-enable controls.
        self.model_combo.config(state="normal")
        if models:
            self.ollama_status_label.config(
                text=f"✓ Ollama reachable at {url} — {len(models)} model(s) "
                     "available.",
            )
            self.model_combo["values"] = models
            cur = self.vars["ollama_model"].get()
            if cur not in models:
                self.vars["ollama_model"].set(models[0])
        else:
            self.ollama_status_label.config(
                text=f"⚠ Ollama is running at {url} but no models are pulled. "
                     "Run e.g. `ollama pull qwen2.5:1.5b`.",
            )
            self.model_combo["values"] = []
            if not quiet:
                messagebox.showinfo(
                    "No Ollama models",
                    f"Connected to {url} but no models are available.\n"
                    "Pull one with `ollama pull qwen2.5:1.5b`.",
                    parent=self.win,
                )

    def _open_voice_manager(self) -> None:
        VoiceManagerDialog(self.win, on_changed=self._refresh_voice_list)

    # ------------------------------------------------------------------
    # Save / Apply / Reset
    # ------------------------------------------------------------------

    def _save(self) -> None:
        """Persist current form values, then close the window."""
        self._persist(close=True)

    def _apply(self) -> None:
        """Persist current form values without closing the window so the
        user can keep tweaking and saving in place."""
        self._persist(close=False)

    def _reset_to_defaults(self) -> None:
        """Replace every form field with its DEFAULT_CONFIG value. Does
        NOT auto-save — user still has to click Apply or Save to commit
        (and Cancel reverts harmlessly because the live config is
        untouched until then)."""
        if not messagebox.askyesno(
            "Reset to defaults",
            "Reset every field to its built-in default? "
            "Click Apply or Save afterwards to keep them.",
            parent=self.win,
        ):
            return
        d = DEFAULT_CONFIG
        self.vars["engine"].set(d["engine"])
        self.vars["voice"].set(d["voice"])
        self.vars["kokoro_voice"].set(d["kokoro_voice"])
        self.vars["speed"].set(round(1.0 / float(d["length_scale"]), 2))
        self.vars["noise_scale"].set(float(d["noise_scale"]))
        self.vars["show_overlay"].set(bool(d["show_overlay"]))
        self.vars["show_text_in_overlay"].set(bool(d["show_text_in_overlay"]))
        self.vars["auto_hide_ms"].set(int(d["auto_hide_ms"]))
        self.vars["overlay_y_offset"].set(int(d["overlay_y_offset"]))
        self.vars["karaoke_offset_ms"].set(int(d["karaoke_offset_ms"]))
        for _aid, key, _label, _default in plugins.hotkey_actions():
            self.vars[key].set(str(d.get(key, "")))
        self.vars["ollama_endpoint"].set(d["ollama_endpoint"])
        self.vars["ollama_model"].set(d["ollama_model"])
        self.vars["ai_translate_target"].set(d["ai_translate_target"])
        self._update_speed_label()
        self._update_var_label()
        self._on_engine_change()

    def _persist(self, *, close: bool) -> None:
        # Build a candidate dict — don't touch self.config until persistence
        # and hotkey rebinding succeed, so a failure never leaves the
        # in-memory state half-committed.
        candidate = dict(self.config)
        eng = self.vars["engine"].get().lower()
        candidate["engine"] = eng
        sel = str(self.vars["voice_display"].get())
        if eng == "kokoro":
            voice_id = sel.split(" — ", 1)[0] if " — " in sel else sel
            candidate["kokoro_voice"] = voice_id.strip()
        else:
            candidate["voice"] = sel

        speed = max(0.4, float(self.vars["speed"].get()))
        candidate["length_scale"] = round(1.0 / speed, 3)
        candidate["noise_scale"] = round(float(self.vars["noise_scale"].get()), 3)
        candidate["show_overlay"] = bool(self.vars["show_overlay"].get())
        candidate["show_text_in_overlay"] = bool(self.vars["show_text_in_overlay"].get())
        candidate["auto_hide_ms"] = int(self.vars["auto_hide_ms"].get())
        candidate["overlay_y_offset"] = int(self.vars["overlay_y_offset"].get())
        candidate["karaoke_offset_ms"] = int(self.vars["karaoke_offset_ms"].get())
        for _aid, key, _label, _default in plugins.hotkey_actions():
            candidate[key] = str(self.vars[key].get()).strip().lower()
        candidate["ollama_endpoint"] = str(self.vars["ollama_endpoint"].get()).strip()
        candidate["ollama_model"] = str(self.vars["ollama_model"].get()).strip()
        candidate["ai_translate_target"] = str(self.vars["ai_translate_target"].get()).strip()

        # Persist first.
        try:
            self.on_save(candidate)
        except Exception as e:
            messagebox.showerror("Save error", str(e), parent=self.win)
            return

        # Snapshot what was different before committing in-memory.
        _hotkey_keys = [a[1] for a in plugins.hotkey_actions()]
        hotkeys_changed = any(
            self.config.get(k, "") != candidate.get(k, "") for k in _hotkey_keys
        )
        engine_changed = self.config.get("engine") != candidate["engine"]

        # Commit to live config.
        self.config.clear()
        self.config.update(candidate)
        # Keep legacy "voice" var in sync so reopening Settings still works.
        if eng == "piper":
            self.vars["voice"].set(sel)

        if hotkeys_changed:
            try:
                failures = self.on_hotkey_change() or []
            except Exception as e:
                messagebox.showwarning(
                    "Hotkey error",
                    f"Could not bind hotkey: {e}\nFormat example: ctrl+shift+x",
                    parent=self.win,
                )
                return
            if failures:
                lines = "\n".join(
                    f"  • {aid} = '{combo}' — {err}"
                    for aid, combo, err in failures
                )
                messagebox.showwarning(
                    "Hotkey error",
                    f"Saved, but these hotkeys could not be bound:\n\n{lines}\n\n"
                    "Format example: ctrl+shift+x",
                    parent=self.win,
                )

        if engine_changed and callable(self.on_engine_change):
            try:
                self.on_engine_change()
            except Exception:
                pass

        if close:
            self._close()
