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
from .theme import UI, make_card


def _encode_download_url(url: str) -> str:
    """Percent-encode the request path for urllib/http.client.

    Hugging Face voice paths can contain non-ASCII speaker names. The
    catalogue keeps them readable, but the HTTP request line must be
    ASCII or urllib can raise before making the request.
    """
    parts = urllib.parse.urlsplit(url)
    safe_path = urllib.parse.quote(parts.path, safe="/")
    return urllib.parse.urlunsplit(parts._replace(path=safe_path))


def _streaming_download(
    url: str,
    dest: Path,
    timeout: float = DOWNLOAD_TIMEOUT_S,
    chunk: int = 1 << 16,
) -> None:
    """Download ``url`` to ``dest`` and fail if the response is empty."""
    encoded_url = _encode_download_url(url)
    with urllib.request.urlopen(encoded_url, timeout=timeout) as resp, dest.open("wb") as f:
        while True:
            buf = resp.read(chunk)
            if not buf:
                break
            f.write(buf)
    if dest.stat().st_size == 0:
        raise RuntimeError("empty response")


def install_piper_voice(
    v: PiperVoice,
    *,
    voices_dir: Path = VOICES_DIR,
    streaming_download: Callable[[str, Path], None] | None = None,
) -> str:
    """Install a curated Piper voice and return the installed model filename."""
    download = streaming_download or _streaming_download
    voices_dir.mkdir(parents=True, exist_ok=True)

    filename = voice_filename(v)
    onnx = voices_dir / filename
    meta = voices_dir / f"{filename}.json"
    part_onnx = onnx.with_suffix(onnx.suffix + ".part")
    part_meta = meta.with_suffix(meta.suffix + ".part")
    base = voice_url_base(v)

    try:
        download(base + filename, part_onnx)
        download(base + f"{filename}.json", part_meta)
        os.replace(str(part_onnx), str(onnx))
        os.replace(str(part_meta), str(meta))
    except Exception:
        for partial in (part_onnx, part_meta):
            try:
                if partial.exists():
                    partial.unlink(missing_ok=True)
            except Exception:
                pass
        raise
    return filename


class VoiceManagerDialog:
    """Modal dialog listing registered Piper voices with install /
    remove buttons. The catalogue comes from `plugins.voices()` —
    extension packages can extend it via `plugins.register_voices`."""

    def __init__(
        self,
        parent: tk.Misc,
        on_changed: Callable[[], None],
        *,
        on_installed: Callable[[str], None] | None = None,
    ) -> None:
        self.parent = parent
        self.on_changed = on_changed
        self.on_installed = on_installed
        self.row_status: dict[str, ttk.Label] = {}
        self.row_buttons: dict[str, ttk.Button] = {}
        self._wheel_handler: Callable[[tk.Event], str] | None = None

        # Snapshot the full registered catalogue once. Filter in-memory
        # on every keystroke / dropdown change. Sorted by language label
        # then by voice id for a stable presentation.
        self._all_voices: list[PiperVoice] = sorted(
            plugins.voices(),
            key=lambda v: (locale_name(v["lang"]), v["id"]),
        )

        d = theme.create_native_dialog(
            parent,
            title="Voices",
            width=820,
            height=620,
            minsize=(760, 520),
            placement="parent-center",
        )
        self.win = d
        d.bind("<Escape>", lambda _e: self._close())
        d.bind("<Alt-F4>", lambda _e: self._close())
        d.protocol("WM_DELETE_WINDOW", self._close)

        # ----- Filter bar -----
        # Keep catalogue filters on the first row and give free-text
        # search its own full-width row so it remains usable at the
        # normal 680 px dialog width.
        filter_bar = ttk.Frame(d, style="TFrame", padding=(20, 20, 20, 0))
        filter_bar.pack(fill="x")
        filter_bar.columnconfigure(5, weight=1)

        ttk.Label(
            filter_bar, text="Language", style="TLabel",
            width=10, anchor="w",
        ).grid(row=0, column=0, sticky="w", padx=(0, 8), pady=(0, 10))
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
        lang_combo.grid(row=0, column=1, sticky="w", padx=(0, 18), pady=(0, 10))
        lang_combo.bind("<<ComboboxSelected>>", lambda _e: self._apply_filter())

        ttk.Label(
            filter_bar, text="Quality", style="TLabel",
            width=8, anchor="w",
        ).grid(row=0, column=2, sticky="w", padx=(0, 8), pady=(0, 10))
        self._quality_choices = ("Any", "high", "medium", "low", "x_low")
        self._quality_var = tk.StringVar(value="Any")
        quality_combo = ttk.Combobox(
            filter_bar, textvariable=self._quality_var,
            values=list(self._quality_choices),
            state="readonly", width=10,
        )
        quality_combo.grid(row=0, column=3, sticky="w", padx=(0, 18), pady=(0, 10))
        quality_combo.bind("<<ComboboxSelected>>",
                           lambda _e: self._apply_filter())

        ttk.Label(
            filter_bar, text="Status", style="TLabel",
            width=7, anchor="w",
        ).grid(row=0, column=4, sticky="w", padx=(0, 8), pady=(0, 10))
        self._status_choices = ("Any", "Installed", "Not installed")
        self._status_var = tk.StringVar(value="Any")
        status_combo = ttk.Combobox(
            filter_bar, textvariable=self._status_var,
            values=list(self._status_choices),
            state="readonly", width=14,
        )
        status_combo.grid(row=0, column=5, sticky="w", pady=(0, 10))
        status_combo.bind("<<ComboboxSelected>>",
                          lambda _e: self._apply_filter())

        ttk.Label(
            filter_bar, text="Search", style="TLabel",
            width=10, anchor="w",
        ).grid(row=1, column=0, sticky="w", padx=(0, 8))
        self._search_var = tk.StringVar(value="")
        search_entry = ttk.Entry(filter_bar, textvariable=self._search_var)
        search_entry.grid(row=1, column=1, columnspan=5, sticky="ew")
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
        def _on_wheel(e: tk.Event) -> str:
            canvas.yview_scroll(int(-e.delta / 120), "units")
            return "break"

        self._wheel_handler = _on_wheel
        d.bind("<MouseWheel>", _on_wheel)
        canvas.bind("<MouseWheel>", _on_wheel)
        inner.bind("<MouseWheel>", _on_wheel)

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
        ttk.Button(footer, text="Close", command=self._close).pack(side="right")

        theme.show_native_dialog(d, parent, grab=True)

    def _close(self) -> None:
        try:
            self.win.grab_release()
        except Exception:
            pass
        try:
            self.win.destroy()
        except Exception:
            pass

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
        if self._wheel_handler is not None:
            self._bind_wheel_recursive(self._rows_parent)

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

    def _bind_wheel_recursive(self, widget: tk.Misc) -> None:
        if self._wheel_handler is None:
            return
        for child in widget.winfo_children():
            if not isinstance(child, (ttk.Button, ttk.Combobox, ttk.Entry)):
                child.bind("<MouseWheel>", self._wheel_handler)
            self._bind_wheel_recursive(child)

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
        try:
            install_piper_voice(v)
            # Window may have been destroyed mid-download — schedule
            # the UI hop only if the dialog is still alive.
            if self._alive():
                self.win.after(0, lambda: self._download_done(v, ok=True))
        except Exception as e:
            err_msg = str(e)
            if self._alive():
                self.win.after(
                    0,
                    lambda msg=err_msg: self._download_done(v, ok=False, err=msg),
                )

    @staticmethod
    def _streaming_download(
        url: str,
        dest: Path,
        timeout: float = DOWNLOAD_TIMEOUT_S,
        chunk: int = 1 << 16,
    ) -> None:
        """Download `url` to `dest` with a connect/read timeout."""
        _streaming_download(url, dest, timeout=timeout, chunk=chunk)

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
            if self.on_installed is not None:
                try:
                    self.on_installed(voice_filename(v))
                except Exception as exc:
                    import sys
                    print(f"[voice_manager] on_installed failed after install: {exc}",
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
