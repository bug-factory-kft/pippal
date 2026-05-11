"""Voice Manager dialog: install/remove curated Piper voices."""

from __future__ import annotations

import os
import threading
import tkinter as tk
import urllib.parse
import urllib.request
from collections.abc import Callable
from pathlib import Path
from tkinter import messagebox, ttk
from typing import Any

from .. import plugins
from ..paths import VOICES_DIR
from ..timing import DOWNLOAD_TIMEOUT_S
from ..voices import (
    PiperVoice,
    installed_voices,
    locale_name,
    voice_filename,
    voice_url_base,
)
from . import theme
from .theme import UI, apply_dark_theme, make_card


def _encode_download_url(url: str) -> str:
    """Percent-encode the request path for urllib/http.client.

    Hugging Face voice paths can contain non-ASCII speaker names. The
    catalogue keeps them readable, but the HTTP request line must be
    ASCII or urllib can raise before making the request.
    """
    parts = urllib.parse.urlsplit(url)
    safe_path = urllib.parse.quote(parts.path, safe="/")
    return urllib.parse.urlunsplit(parts._replace(path=safe_path))


class VoiceManagerDialog:
    """Modal dialog listing registered Piper voices with install /
    remove buttons. The catalogue comes from `plugins.voices()` —
    extension packages can extend it via `plugins.register_voices`."""

    def __init__(self, parent: tk.Misc, on_changed: Callable[[], None]) -> None:
        self.parent = parent
        self.on_changed = on_changed
        self.row_status: dict[str, ttk.Label] = {}
        self.row_buttons: dict[str, ttk.Button] = {}

        # Snapshot the full registered catalogue once. Filter in-memory
        # on every keystroke / dropdown change. Sorted by language label
        # then by voice id for a stable presentation.
        self._all_voices: list[PiperVoice] = sorted(
            plugins.voices(),
            key=lambda v: (locale_name(v["lang"]), v["id"]),
        )

        d = tk.Toplevel(parent)
        self.win = d
        # No native title — we draw our own header to match the main
        # Settings window. Set a title anyway so the taskbar/Alt+Tab
        # entry has a name before the chromeless subclass runs.
        d.title("Voices")
        d.minsize(620, 500)
        d.transient(parent)
        d.grab_set()

        # Open at the same on-screen position as the parent window
        # (the Settings dialog), not via WM-default placement. The
        # user expects "the same place as the main window" — use the
        # parent's geometry as the origin and clamp to the screen.
        win_w, win_h = 680, 600
        try:
            px = parent.winfo_x()
            py = parent.winfo_y()
            sw = d.winfo_screenwidth()
            sh = d.winfo_screenheight()
            x = max(0, min(px, sw - win_w))
            y = max(0, min(py, sh - win_h))
        except Exception:
            x, y = 100, 100
        d.geometry(f"{win_w}x{win_h}+{x}+{y}")

        apply_dark_theme(d)

        # Replicate the SettingsWindow chromeless setup: hide the
        # native title bar via the WM_NCCALCSIZE subclass, restore
        # Win 11 rounded corners, and hand the user Esc / Alt+F4 to
        # close (no system menu without the caption strip).
        self._did_chromeless = False

        def _apply_chromeless(_e: tk.Event | None = None) -> None:
            if self._did_chromeless:
                return
            self._did_chromeless = True
            theme.make_chromeless_keep_taskbar(d)
            theme.apply_rounded_corners(d)

        d.bind("<Map>", _apply_chromeless)
        d.after(50, _apply_chromeless)
        d.bind("<Escape>", lambda _e: d.destroy())
        d.bind("<Alt-F4>", lambda _e: d.destroy())

        header = ttk.Frame(d, style="Header.TFrame", padding=(24, 14, 8, 14))
        header.pack(fill="x")

        # Right-edge ✕ button — packed first so the title row can
        # claim the rest of the width.
        ttk.Button(
            header, text="✕", style="TitleClose.TButton",
            command=d.destroy, width=3, takefocus=False,
        ).pack(side="right", padx=(0, 4))

        title_row = ttk.Frame(header, style="Header.TFrame")
        title_row.pack(side="left", fill="x", expand=True)

        # PipPal logo on the left of the custom title bar — held on
        # `self` so Tk doesn't garbage-collect the bitmap mid-render.
        self._title_icon_photo: Any = None
        try:
            from PIL import Image, ImageTk

            from ..tray import _load_and_fit_icon
            _lanczos = getattr(Image, "Resampling", Image).LANCZOS
            self._title_icon_photo = ImageTk.PhotoImage(
                _load_and_fit_icon().resize((22, 22), _lanczos),
            )
            tk.Label(
                title_row, image=self._title_icon_photo,
                bg=UI["bg"], borderwidth=0,
            ).pack(side="left", padx=(0, 10))
        except Exception:
            pass

        ttk.Label(title_row, text="Voices", style="Title.TLabel").pack(side="left")
        n = len(self._all_voices)
        ttk.Label(
            title_row,
            text=(f"{n} voice{'s' if n != 1 else ''} available · "
                  "click Install to download."),
            style="Sub.TLabel",
        ).pack(side="left", padx=(10, 0), pady=(7, 0))

        # Without a native title bar the user can't drag to move; bind
        # the whole header (skipping interactive widgets like the ✕
        # button) so the panel still feels like a normal window.
        theme.enable_drag_to_move(d, header)

        # ----- Filter bar -----
        # Language dropdown + free-text search. Both drive the same
        # `_apply_filter` rebuild below. The dropdown's first entry
        # ('All languages') is the unfiltered case.
        filter_bar = ttk.Frame(d, style="TFrame", padding=(20, 12, 20, 0))
        filter_bar.pack(fill="x")

        ttk.Label(filter_bar, text="Language", style="TLabel",
                  width=10, anchor="w").pack(side="left")
        unique_locales = sorted({v["lang"] for v in self._all_voices},
                                 key=locale_name)
        self._lang_choices: list[tuple[str, str]] = [
            ("__all__", "All languages")
        ] + [(code, locale_name(code)) for code in unique_locales]
        self._lang_var = tk.StringVar(value="All languages")
        lang_combo = ttk.Combobox(
            filter_bar, textvariable=self._lang_var,
            values=[label for _code, label in self._lang_choices],
            state="readonly", width=22,
        )
        lang_combo.pack(side="left", padx=(0, 16))
        lang_combo.bind("<<ComboboxSelected>>", lambda _e: self._apply_filter())

        # Quality filter — Piper publishes voices at four quality
        # levels (x_low / low / medium / high). Default to 'Any' so
        # the user sees everything; filter down once they care.
        ttk.Label(filter_bar, text="Quality", style="TLabel",
                  width=8, anchor="w").pack(side="left")
        self._quality_choices = ("Any", "high", "medium", "low", "x_low")
        self._quality_var = tk.StringVar(value="Any")
        quality_combo = ttk.Combobox(
            filter_bar, textvariable=self._quality_var,
            values=list(self._quality_choices),
            state="readonly", width=10,
        )
        quality_combo.pack(side="left", padx=(0, 16))
        quality_combo.bind("<<ComboboxSelected>>",
                           lambda _e: self._apply_filter())

        # Installed filter — three states: Any / Installed only /
        # Not installed only. Useful when the user has dozens of
        # downloads and wants to see at a glance what's already on
        # disk vs. what could still be added.
        ttk.Label(filter_bar, text="Status", style="TLabel",
                  width=7, anchor="w").pack(side="left")
        self._status_choices = ("Any", "Installed", "Not installed")
        self._status_var = tk.StringVar(value="Any")
        status_combo = ttk.Combobox(
            filter_bar, textvariable=self._status_var,
            values=list(self._status_choices),
            state="readonly", width=14,
        )
        status_combo.pack(side="left", padx=(0, 16))
        status_combo.bind("<<ComboboxSelected>>",
                          lambda _e: self._apply_filter())

        ttk.Label(filter_bar, text="Search", style="TLabel",
                  width=8, anchor="w").pack(side="left")
        self._search_var = tk.StringVar(value="")
        search_entry = ttk.Entry(filter_bar, textvariable=self._search_var)
        search_entry.pack(side="left", fill="x", expand=True)
        # Debounce the trace: rebuilding 100+ rows on every keystroke
        # is noticeably laggy. Wait 180 ms after the last edit before
        # re-running the filter, but always apply on Enter.
        self._filter_after_id: str | None = None
        self._search_var.trace_add("write", lambda *_a: self._schedule_filter())
        search_entry.bind("<Return>", lambda _e: self._apply_filter())

        # ----- Scrollable body for the rows -----
        body_outer = ttk.Frame(d, style="TFrame")
        body_outer.pack(fill="both", expand=True, padx=20, pady=(8, 0))

        canvas = tk.Canvas(body_outer, bg=UI["bg"], highlightthickness=0)
        canvas.pack(side="left", fill="both", expand=True)
        sb = ttk.Scrollbar(
            body_outer, orient="vertical", command=canvas.yview,
            style="Vertical.TScrollbar",
        )
        sb.pack(side="right", fill="y")
        canvas.configure(yscrollcommand=sb.set)
        inner = ttk.Frame(canvas, style="TFrame")
        inner_id = canvas.create_window((0, 0), window=inner, anchor="nw")

        def _resize(e: tk.Event) -> None:
            canvas.configure(scrollregion=canvas.bbox("all"))
            canvas.itemconfig(inner_id, width=e.width)

        canvas.bind("<Configure>", _resize)
        inner.bind(
            "<Configure>",
            lambda _e: canvas.configure(scrollregion=canvas.bbox("all")),
        )
        canvas.bind(
            "<MouseWheel>",
            lambda e: canvas.yview_scroll(int(-e.delta / 120), "units"),
        )
        # Also bind the mousewheel on the inner frame so scrolling
        # works while the cursor is over a row, not just the canvas
        # gutter.
        inner.bind(
            "<MouseWheel>",
            lambda e: canvas.yview_scroll(int(-e.delta / 120), "units"),
        )

        # Cache widgets we'll need to rebuild per filter change.
        self._rows_parent = inner
        self._canvas = canvas
        self._empty_label: ttk.Label | None = None

        # Initial population.
        self._apply_filter()

        footer = ttk.Frame(d, style="Header.TFrame", padding=(24, 12, 24, 16))
        footer.pack(fill="x", side="bottom")
        sep = tk.Frame(d, bg=UI["border"], height=1)
        sep.pack(fill="x", side="bottom", before=footer)
        ttk.Button(footer, text="Close", command=d.destroy).pack(side="right")

    def _schedule_filter(self) -> None:
        """Coalesce typing bursts into a single rebuild. Called on every
        keystroke; the actual filter runs once 400 ms after the last
        edit so even slow typists don't get a stutter halfway through
        a word. Enter still applies immediately."""
        if self._filter_after_id is not None:
            try:
                self.win.after_cancel(self._filter_after_id)
            except Exception:
                pass
        self._filter_after_id = self.win.after(400, self._apply_filter)

    def _apply_filter(self) -> None:
        """Rebuild the list of rows according to the current filter
        widgets. Cheap because we only have ~hundreds of voices at
        worst and Tk widget creation per row is fast."""
        # Clear existing rows + the row-state caches.
        for child in self._rows_parent.winfo_children():
            child.destroy()
        self.row_status.clear()
        self.row_buttons.clear()
        self._empty_label = None

        # Resolve the chosen language filter back to the locale code.
        chosen_label = self._lang_var.get()
        chosen_code = "__all__"
        for code, label in self._lang_choices:
            if label == chosen_label:
                chosen_code = code
                break
        chosen_quality = self._quality_var.get()
        chosen_status = self._status_var.get()
        query = self._search_var.get().strip().lower()

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
            self._build_row(self._rows_parent, v, installed)
            rows += 1

        if rows == 0:
            self._empty_label = ttk.Label(
                self._rows_parent,
                text="No voices match. Clear the filter to see everything.",
                style="CardHint.TLabel",
            )
            self._empty_label.pack(anchor="w", pady=(20, 0))

        # Update scrollregion now that the row count changed.
        self._rows_parent.update_idletasks()
        self._canvas.configure(scrollregion=self._canvas.bbox("all"))

    def _build_row(self, parent: tk.Misc, v: PiperVoice, installed: set[str]) -> None:
        outer, card = make_card(parent)
        outer.pack(fill="x", pady=(0, 10))
        row = ttk.Frame(card, style="Card.TFrame")
        row.pack(fill="x")

        left = ttk.Frame(row, style="Card.TFrame")
        left.pack(side="left", fill="x", expand=True)
        ttk.Label(left, text=v["label"], style="Card.TLabel",
                  font=("Segoe UI Semibold", 10)).pack(anchor="w")
        ttk.Label(left, text=f"id: {v['id']}   ·   {v['quality']}",
                  style="CardHint.TLabel").pack(anchor="w", pady=(2, 0))

        right = ttk.Frame(row, style="Card.TFrame")
        right.pack(side="right")

        status = ttk.Label(right, text="", style="CardHint.TLabel")
        status.pack(side="left", padx=(0, 10))
        self.row_status[v["id"]] = status

        if voice_filename(v) in installed:
            status.config(text="✓ installed")
            btn = ttk.Button(right, text="Remove", style="Danger.TButton",
                             command=lambda vv=v: self._remove(vv))
        else:
            btn = ttk.Button(right, text="Install", style="Card.TButton",
                             command=lambda vv=v: self._download(vv))
        btn.pack(side="left")
        self.row_buttons[v["id"]] = btn

    def _alive(self) -> bool:
        try:
            return bool(self.win.winfo_exists())
        except Exception:
            return False

    def _download(self, v: PiperVoice) -> None:
        self.row_status[v["id"]].config(text="downloading…")
        btn = self.row_buttons.get(v["id"])
        if btn is not None:
            btn.config(state="disabled")
        threading.Thread(target=self._download_thread, args=(v,), daemon=True).start()

    def _download_thread(self, v: PiperVoice) -> None:
        base = voice_url_base(v)
        onnx = VOICES_DIR / f"{v['id']}.onnx"
        meta = VOICES_DIR / f"{v['id']}.onnx.json"
        part_onnx = onnx.with_suffix(onnx.suffix + ".part")
        part_meta = meta.with_suffix(meta.suffix + ".part")
        try:
            self._streaming_download(base + f"{v['id']}.onnx", part_onnx)
            self._streaming_download(base + f"{v['id']}.onnx.json", part_meta)
            os.replace(str(part_onnx), str(onnx))
            os.replace(str(part_meta), str(meta))
            # Window may have been destroyed mid-download — schedule
            # the UI hop only if the dialog is still alive.
            if self._alive():
                self.win.after(0, lambda: self._download_done(v, ok=True))
        except Exception as e:
            err_msg = str(e)
            for partial in (part_onnx, part_meta):
                try:
                    if partial.exists():
                        partial.unlink(missing_ok=True)
                except Exception:
                    pass
            if self._alive():
                self.win.after(0,
                               lambda msg=err_msg: self._download_done(v, ok=False, err=msg))

    @staticmethod
    def _streaming_download(url: str, dest: Path,
                             timeout: float = DOWNLOAD_TIMEOUT_S,
                             chunk: int = 1 << 16) -> None:
        """Download `url` to `dest` with a connect/read timeout. Raises
        if the request hangs or the response is empty."""
        encoded_url = _encode_download_url(url)
        with urllib.request.urlopen(encoded_url, timeout=timeout) as resp, \
             dest.open("wb") as f:
            while True:
                buf = resp.read(chunk)
                if not buf:
                    break
                f.write(buf)
        if dest.stat().st_size == 0:
            raise RuntimeError("empty response")

    def _download_done(self, v: PiperVoice, ok: bool, err: Any = None) -> None:
        # The schedule was guarded by `_alive()`, but the dialog could
        # still get destroyed in the gap before this runs on the UI
        # thread — re-check before touching widgets.
        if not self._alive():
            return
        if ok:
            self.row_status[v["id"]].config(text="✓ installed")
            btn = self.row_buttons.get(v["id"])
            if btn is not None:
                btn.config(state="normal", text="Remove", style="Danger.TButton",
                           command=lambda vv=v: self._remove(vv))
            # Log to stderr instead of silent swallow — a previous user
            # report ("voice combo didn't refresh, but only once") would
            # have shown its root cause if we'd been printing.
            try:
                self.on_changed()
            except Exception as exc:
                import sys
                print(f"[voice_manager] on_changed failed after install: {exc}",
                      file=sys.stderr)
        else:
            self.row_status[v["id"]].config(text="failed")
            btn = self.row_buttons.get(v["id"])
            if btn is not None:
                btn.config(state="normal")
            messagebox.showerror("Download failed", str(err), parent=self.win)

    def _remove(self, v: PiperVoice) -> None:
        if not messagebox.askyesno("Remove voice",
                                   f"Remove {v['label']}?",
                                   parent=self.win):
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
            print(f"[voice_manager] on_changed failed after remove: {exc}",
                  file=sys.stderr)
        self.row_status[v["id"]].config(text="—")
        btn = self.row_buttons.get(v["id"])
        if btn is not None:
            btn.config(text="Install", style="Card.TButton",
                       command=lambda vv=v: self._download(vv))
