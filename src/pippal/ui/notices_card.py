"""Settings card that surfaces bundled third-party licence notices."""

from __future__ import annotations

import tkinter as tk
from collections.abc import Iterable
from pathlib import Path
from tkinter import ttk
from typing import TYPE_CHECKING, Any

from pippal.paths import INSTALL_ROOT
from pippal.ui import theme
from pippal.ui.theme import UI, apply_dark_theme, make_card

if TYPE_CHECKING:  # pragma: no cover
    from pippal.ui.settings_window import SettingsWindow


_NOTICES_CANDIDATES: tuple[str, ...] = (
    "NOTICES.txt",
    "packaging/build/NOTICES.txt",
    "docs/THIRD_PARTY.md",
)


def _candidate_notice_roots() -> tuple[Path, ...]:
    here = Path(__file__).resolve()
    roots = [
        INSTALL_ROOT,
        here.parents[2],
        here.parents[3],
    ]
    unique: list[Path] = []
    for root in roots:
        resolved = root.resolve()
        if resolved not in unique:
            unique.append(resolved)
    return tuple(unique)


def _resolve_notices_path(roots: Iterable[Path] | None = None) -> Path | None:
    for root in roots or _candidate_notice_roots():
        for rel in _NOTICES_CANDIDATES:
            path = root / rel
            if path.exists():
                return path
    return None


def build_notices_card(sw: SettingsWindow, body: ttk.Frame) -> None:
    outer, card = make_card(body, "Open-source notices")
    outer.pack(fill="x", pady=(0, 12))

    ttk.Label(
        card,
        text=(
            "PipPal uses open-source libraries and local TTS runtime artifacts. "
            "Their licences are included with this install or source checkout."
        ),
        style="CardHint.TLabel",
        wraplength=520,
        justify="left",
    ).pack(anchor="w")

    notices_path = _resolve_notices_path()
    brand_name = str(sw.config.get("brand_name", "PipPal"))

    def _open_notices() -> None:
        if sw.win is None:
            return
        sw.win._pippal_notices_viewer = _NoticesViewer(sw.win, notices_path, brand_name)

    btn_row = ttk.Frame(card, style="Card.TFrame")
    btn_row.pack(anchor="w", pady=(8, 0))
    ttk.Button(
        btn_row,
        text="View licences…",
        style="Card.TButton",
        command=_open_notices,
    ).pack(side="left")


def _notices_text_options() -> dict[str, object]:
    return {
        "wrap": "word",
        "bg": UI["bg_card"],
        "fg": UI["text"],
        "font": ("Consolas", 9),
        "relief": "flat",
        "highlightthickness": 0,
    }


class _NoticesViewer:
    """Modal Toplevel that scrolls the notices file. Read-only."""

    def __init__(self, parent: tk.Misc, path: Path | None, brand_name: str) -> None:
        self._title_icon_photo: Any = None
        self._did_chromeless = False
        self.path = path
        self.brand_name = brand_name

        d = tk.Toplevel(parent)
        d.withdraw()
        self.win = d
        d._pippal_notices_viewer = self
        d.title(f"{brand_name} - Open-source licences")
        d.minsize(640, 400)
        d.transient(parent)

        w, h = 760, 600
        try:
            px = parent.winfo_x()
            py = parent.winfo_y()
            sw = d.winfo_screenwidth()
            sh = d.winfo_screenheight()
            x = max(0, min(px, sw - w))
            y = max(0, min(py, sh - h))
        except Exception:
            x = (d.winfo_screenwidth() - w) // 2
            y = (d.winfo_screenheight() - h) // 2
        d.geometry(f"{w}x{h}+{x}+{y}")

        apply_dark_theme(d)
        self._install_chromeless_handlers(d)
        d.bind("<Escape>", lambda _e: d.destroy())
        d.bind("<Alt-F4>", lambda _e: d.destroy())

        self._build_header(d)

        wrap = ttk.Frame(d, style="TFrame", padding=(20, 0, 20, 18))
        wrap.pack(fill="both", expand=True)

        text = tk.Text(wrap, **_notices_text_options())
        text.pack(side="left", fill="both", expand=True)

        sb = ttk.Scrollbar(
            wrap,
            orient="vertical",
            command=text.yview,
            style="Vertical.TScrollbar",
        )
        sb.pack(side="right", fill="y")
        text.configure(yscrollcommand=sb.set)

        text.insert("1.0", self._load_text())
        text.configure(state="disabled")

        d.protocol("WM_DELETE_WINDOW", d.destroy)
        d.update_idletasks()
        d.deiconify()
        d.lift(parent)
        d.focus_force()
        d.grab_set()

    def _install_chromeless_handlers(self, d: tk.Toplevel) -> None:
        if self._did_chromeless:
            return
        self._did_chromeless = True
        # Apply chromeless styling before the first visible map. If this
        # runs after mapping, Windows can briefly show the native caption.
        d.overrideredirect(True)
        theme.apply_rounded_corners(d)
        d.after_idle(lambda: theme.apply_rounded_corners(d) if d.winfo_exists() else None)

    def _build_header(self, d: tk.Toplevel) -> None:
        header = ttk.Frame(d, style="Header.TFrame", padding=(24, 14, 8, 14))
        header.pack(fill="x")

        ttk.Button(
            header,
            text="✕",
            style="TitleClose.TButton",
            command=d.destroy,
            width=3,
            takefocus=False,
        ).pack(side="right", padx=(0, 4))

        title_row = ttk.Frame(header, style="Header.TFrame")
        title_row.pack(side="left", fill="x", expand=True)

        try:
            from PIL import Image, ImageTk

            from pippal.tray import _load_and_fit_icon

            lanczos = getattr(Image, "Resampling", Image).LANCZOS
            self._title_icon_photo = ImageTk.PhotoImage(
                _load_and_fit_icon().resize((22, 22), lanczos),
            )
            tk.Label(
                title_row,
                image=self._title_icon_photo,
                bg=UI["bg"],
                borderwidth=0,
            ).pack(side="left", padx=(0, 10))
        except Exception:
            pass

        ttk.Label(
            title_row,
            text="Open-source licences",
            style="Title.TLabel",
        ).pack(side="left")
        ttk.Label(
            title_row,
            text="Bundled third-party notices",
            style="Sub.TLabel",
        ).pack(side="left", padx=(10, 0), pady=(7, 0))

        theme.enable_drag_to_move(d, header)

    def _load_text(self) -> str:
        if self.path is None:
            return (
                "Open-source notices were not found.\n\n"
                "Please reinstall PipPal to restore the licences file, or open "
                "docs/THIRD_PARTY.md from the source checkout."
            )
        try:
            return self.path.read_text(encoding="utf-8")
        except Exception as exc:
            return (
                f"Could not read {self.path}\n\n{exc}\n\n"
                "Please reinstall PipPal to restore the licences file."
            )
