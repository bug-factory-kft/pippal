"""The Settings window — dark, card-based, with engine / voice / hotkey
/ AI / panel / Windows-integration sections."""

from __future__ import annotations

import tkinter as tk
from collections.abc import Callable
from tkinter import messagebox, ttk
from typing import Any

from .. import plugins
from ..context_menu import (
    context_menu_status,
    install_context_menu,
    uninstall_context_menu,
)
from ..voices import installed_voices
from . import theme
from .theme import UI, apply_dark_theme
from .voice_manager import VoiceManagerDialog


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
        # Remember last window position so the user reopens it where
        # they left it. None on first open → screen-centre fallback.
        self._last_position: tuple[int, int] | None = None
        # PhotoImage for the title-bar icon. Has to outlive the window
        # so Tk doesn't garbage-collect the bitmap mid-render.
        self._title_icon_photo: Any = None
        # Wheel handler reference so the post-build pass can reuse it.
        self._wheel_handler: Callable[[tk.Event], str] | None = None

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
        # Compute initial geometry: last-known position, otherwise
        # centre on the screen the root window is on.
        win_w, win_h = 600, 700
        if self._last_position is not None:
            x, y = self._last_position
        else:
            sw = w.winfo_screenwidth()
            sh = w.winfo_screenheight()
            x = max(0, (sw - win_w) // 2)
            y = max(0, (sh - win_h) // 2)
        w.geometry(f"{win_w}x{win_h}+{x}+{y}")
        w.minsize(560, 600)
        apply_dark_theme(w)
        self._install_chromeless_handlers(w)
        # The chromeless window has no system menu; bind Esc + Alt+F4
        # so the user has both standard ways to close it.
        w.bind("<Escape>", lambda _e: self._close())
        w.bind("<Alt-F4>", lambda _e: self._close())

        self._build_header(w)
        body = self._build_scrollable_body(w)
        # Cards are registered into the plugin host (pippal.plugins) by
        # whichever package supplies them — the core pippal package
        # registers Voice/Speech/Hotkeys/Panel/Integration/About via
        # `_register.py`; extensions can add their own cards. The order
        # comes from each registration's `zone` (with `order` as a
        # tie-breaker).
        for builder in plugins.settings_cards():
            builder(self, body)
        # All cards are now in. Walk the tree once and bind
        # `<MouseWheel>` on each widget so the user can scroll from
        # any spot in the form, not just on the scrollbar.
        self._bind_wheel_recursive(body)
        self._build_footer(w)

        w.protocol("WM_DELETE_WINDOW", self._close)

    def _install_chromeless_handlers(self, w: tk.Toplevel) -> None:
        # Hide the native title bar via the canonical Win32 WndProc
        # subclass — WM_NCCALCSIZE returns 0 so Windows treats the
        # whole window as client area, no caption strip drawn. The
        # window remains a normal app window from the WM's view, so
        # taskbar / Alt+Tab / focus all keep working.
        #
        # Tk creates the HWND lazily; firing on `<Map>` (the moment
        # the window becomes visible) is more reliable than a blind
        # `after(10, ...)` timer. The guard is scoped to this specific
        # Toplevel, so a later Settings reopen gets its own setup pass.
        did_chromeless = False

        def _apply_chromeless(_e: tk.Event | None = None) -> None:
            nonlocal did_chromeless
            if did_chromeless:
                return
            did_chromeless = True
            theme.make_chromeless_keep_taskbar(w)
            theme.apply_rounded_corners(w)

        w.bind("<Map>", _apply_chromeless)
        # Also fire after 50 ms in case the window is mapped before
        # the binding takes effect (race-y on some Tk builds).
        w.after(50, _apply_chromeless)

    def _close(self) -> None:
        if self.win is not None:
            try:
                # Snapshot position so the next open lands here.
                self._last_position = (self.win.winfo_x(), self.win.winfo_y())
            except Exception:
                pass
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
        header = ttk.Frame(w, style="Header.TFrame", padding=(24, 14, 8, 14))
        header.pack(fill="x")

        # Custom-titlebar window controls. Just a close button — this
        # is a fixed-size dialog, no min/max needed. Pack it first so
        # the title row gets `expand=True` and the ✕ stays right-edge.
        ttk.Button(
            header, text="✕", style="TitleClose.TButton",
            command=self._close, width=3, takefocus=False,
        ).pack(side="right", padx=(0, 4))

        title_row = ttk.Frame(header, style="Header.TFrame")
        title_row.pack(side="left", fill="x", expand=True)

        # PipPal logo in the custom title bar — same asset as the
        # tray, downscaled to ~22 px for the header. We hold the
        # PhotoImage on `self` so Tk doesn't GC it under the window.
        try:
            from PIL import Image, ImageTk

            from ..tray import _load_and_fit_icon
            _lanczos = getattr(Image, "Resampling", Image).LANCZOS
            icon_64 = _load_and_fit_icon()
            icon_22 = icon_64.resize((22, 22), _lanczos)
            self._title_icon_photo = ImageTk.PhotoImage(icon_22)
            tk.Label(
                title_row, image=self._title_icon_photo,
                bg=UI["bg"], borderwidth=0,
            ).pack(side="left", padx=(0, 10))
        except Exception:
            # Fallback: the previous accent-coloured dot, in case the
            # asset / Pillow ImageTk is unavailable for any reason.
            dot = tk.Canvas(title_row, width=14, height=14,
                            bg=UI["bg"], highlightthickness=0)
            dot.create_oval(2, 2, 12, 12, fill=UI["accent"], outline="")
            dot.pack(side="left", padx=(0, 10))
        ttk.Label(title_row, text=brand, style="Title.TLabel").pack(side="left")
        # Inline subtitle next to the brand, baseline-shifted so it
        # sits one row with the brand and the right-side ✕ button
        # rather than dangling below them.
        ttk.Label(
            title_row, text="Settings", style="Sub.TLabel",
        ).pack(side="left", padx=(10, 0), pady=(7, 0))

        # Native title bar is hidden — without `enable_drag_to_move`
        # the user couldn't move the window. Drag handlers go on the
        # whole header; clicks on the ✕ button or any interactive
        # widget pass through unaffected.
        theme.enable_drag_to_move(w, header)

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

        # Mouse-wheel scrolling everywhere inside the body, not just
        # over the canvas. Bind on the *window* with `bind` (not
        # `bind_all` — that hijacks scroll across the whole app).
        # `<MouseWheel>` doesn't propagate up by default, so we also
        # walk every child and re-bind. Children added later (the
        # cards built by plugin builders) get bound by a tail call
        # in `open()` once they're all in.
        def _on_wheel(e: tk.Event) -> str:
            canvas.yview_scroll(int(-e.delta / 120), "units")
            return "break"

        self._wheel_handler = _on_wheel  # cached for plugin-card pass
        w.bind("<MouseWheel>", _on_wheel)
        canvas.bind("<MouseWheel>", _on_wheel)
        body.bind("<MouseWheel>", _on_wheel)
        return body

    def _bind_wheel_recursive(self, widget: tk.Misc) -> None:
        """Re-bind `<MouseWheel>` on every descendant so the body
        scrolls regardless of which widget the cursor is over.
        Called once after the plugin settings cards are built."""
        if self._wheel_handler is None:
            return
        for child in widget.winfo_children():
            try:
                child.bind("<MouseWheel>", self._wheel_handler)
            except Exception:
                pass
            self._bind_wheel_recursive(child)

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
        # Voice list refresh is engine-agnostic: rebuild whichever
        # engine is currently selected. Engine plugins decide for
        # themselves whether their voice combo content depends on
        # disk state (Piper) or is a static catalogue.
        if "engine" in self.vars:
            self._on_engine_change()

    def _on_engine_change(self) -> None:
        """Re-populate the Voice card after the user picks an engine.

        The default behaviour here covers the always-registered Piper
        engine: list installed `.onnx` files, nudge the user toward
        Manage…, and tell every registered handler about the change
        so engine-specific extensions can show / hide their own
        widgets and override the voice combo content."""
        eng = self.vars["engine"].get()

        # Default Piper-style population. Plugin handlers below may
        # override the voice combo for their own engine.
        installed = installed_voices()
        if installed:
            self.voice_combo["values"] = installed
            self.voice_combo.configure(state="readonly")
            cur = str(self.vars["voice"].get())
            self.vars["voice_display"].set(
                cur if cur in installed else installed[0]
            )
            self.engine_hint.config(
                text="Piper voice. Click Manage to install more from the "
                     "curated list.",
            )
            self.manage_btn.configure(text="Manage…")
        else:
            # Empty Piper install — don't pretend a voice is selected;
            # show a disabled placeholder and turn the Manage button
            # into the call-to-action so the user can't miss it.
            placeholder = "(no voice installed)"
            self.voice_combo["values"] = [placeholder]
            self.vars["voice_display"].set(placeholder)
            self.voice_combo.configure(state="disabled")
            self.engine_hint.config(
                text="No Piper voice installed yet. Click Install voices "
                     "to download one.",
            )
            self.manage_btn.configure(text="Install voices…")
        self.manage_btn.pack(side="left", padx=(10, 0))

        # Engine-specific handlers — they self-filter on `eng`.
        for handler in plugins.voice_card_engine_handlers():
            try:
                handler(self, eng)
            except Exception as exc:
                import sys
                print(f"[settings] engine handler error: {exc}",
                      file=sys.stderr)

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
        # `_layered_defaults` includes plugin contributions, so when
        # extension cards are present their keys are in `d` and we'll
        # reset them; when absent, we silently skip.
        from ..config import _layered_defaults
        d = _layered_defaults()

        # Helper vars without a direct config-key counterpart. `speed`
        # is the inverse of `length_scale`; `voice_display` is just
        # the rendered combo label.
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
        # Build a candidate dict — don't touch self.config until persistence
        # and hotkey rebinding succeed, so a failure never leaves the
        # in-memory state half-committed.
        candidate = dict(self.config)
        eng = self.vars["engine"].get().lower()
        candidate["engine"] = eng

        # Engine-specific persist hooks decide what gets written for
        # the current engine. The built-in Piper hook reads
        # ``voice_display`` into ``voice``; an extension's hook may
        # set its own per-engine config keys.
        for hook in plugins.voice_card_persist_hooks():
            try:
                hook(self, eng, candidate)
            except Exception as exc:
                import sys
                print(f"[settings] persist hook error: {exc}",
                      file=sys.stderr)

        # `speed` is the user-facing inverse of length_scale.
        speed = max(0.4, float(self.vars["speed"].get()))
        candidate["length_scale"] = round(1.0 / speed, 3)

        # Persist whatever else cards have registered. Any vars they
        # added become candidate keys automatically, so an extension
        # package's settings get saved without the core knowing the
        # key names.
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
                # Hotkey combos are case-insensitive; normalise here so
                # config diffs don't churn on capitalisation.
                if key.startswith("hotkey_"):
                    value = value.lower()
            candidate[key] = value

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

        # Commit to live config.
        self.config.clear()
        self.config.update(candidate)
        # Keep legacy "voice" var in sync so reopening Settings still
        # works on Piper. Other engines manage their own var content
        # via the plugin host hooks above.
        if eng == "piper" and "voice" in candidate:
            self.vars["voice"].set(str(candidate["voice"]))

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

        # Always tell the engine to drop its cached backend after a
        # successful Apply. The backend snapshot-copies its config at
        # construction (engines/base.py), so any live config update —
        # voice change, length_scale, anything per-backend — needs a
        # rebuild on the next synth. The reset itself is a tiny lock
        # +  three attribute assigns, so calling it unconditionally is
        # cheaper than keeping per-engine "what counts as changed?"
        # logic in the public package.
        if callable(self.on_engine_change):
            try:
                self.on_engine_change()
            except Exception:
                pass

        if close:
            self._close()
