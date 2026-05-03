"""Voice Manager dialog: install/remove curated Piper voices."""

from __future__ import annotations

import os
import threading
import tkinter as tk
import urllib.request
from collections.abc import Callable
from pathlib import Path
from tkinter import messagebox, ttk
from typing import Any

from ..paths import VOICES_DIR
from ..timing import DOWNLOAD_TIMEOUT_S
from ..voices import KNOWN_VOICES, PiperVoice, installed_voices, voice_filename, voice_url_base
from .theme import UI, apply_dark_theme, make_card


class VoiceManagerDialog:
    """Modal dialog listing known Piper voices with install/remove buttons."""

    def __init__(self, parent: tk.Misc, on_changed: Callable[[], None]) -> None:
        self.parent = parent
        self.on_changed = on_changed
        self.row_status: dict[str, ttk.Label] = {}
        self.row_buttons: dict[str, ttk.Button] = {}

        d = tk.Toplevel(parent)
        self.win = d
        d.title("Voices")
        d.geometry("680x520")
        d.minsize(620, 460)
        d.transient(parent)
        d.grab_set()

        apply_dark_theme(d)

        header = ttk.Frame(d, style="Header.TFrame", padding=(24, 18, 24, 14))
        header.pack(fill="x")
        ttk.Label(header, text="Voices", style="Title.TLabel").pack(anchor="w")
        ttk.Label(
            header,
            text="Click Install on a voice to download it from Hugging Face.",
            style="Sub.TLabel",
        ).pack(anchor="w", pady=(2, 0))

        body_outer = ttk.Frame(d, style="TFrame")
        body_outer.pack(fill="both", expand=True, padx=20)

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
        # Local bind (was bind_all) — see settings_window.py for rationale.
        canvas.bind(
            "<MouseWheel>",
            lambda e: canvas.yview_scroll(int(-e.delta / 120), "units"),
        )

        installed = set(installed_voices())
        for v in KNOWN_VOICES:
            self._build_row(inner, v, installed)

        footer = ttk.Frame(d, style="Header.TFrame", padding=(24, 12, 24, 16))
        footer.pack(fill="x", side="bottom")
        sep = tk.Frame(d, bg=UI["border"], height=1)
        sep.pack(fill="x", side="bottom", before=footer)
        ttk.Button(footer, text="Close", command=d.destroy).pack(side="right")

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
        with urllib.request.urlopen(url, timeout=timeout) as resp, \
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
            try:
                self.on_changed()
            except Exception:
                pass
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
        except Exception:
            pass
        self.row_status[v["id"]].config(text="—")
        btn = self.row_buttons.get(v["id"])
        if btn is not None:
            btn.config(text="Install", style="Card.TButton",
                       command=lambda vv=v: self._download(vv))
