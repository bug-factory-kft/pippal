"""Settings card that surfaces bundled third-party licence notices."""

from __future__ import annotations

import tkinter as tk
from collections.abc import Iterable
from pathlib import Path
from tkinter import ttk
from typing import TYPE_CHECKING

from pippal.paths import INSTALL_ROOT
from pippal.ui import theme
from pippal.ui.theme import UI, make_card

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
        self.path = path
        self.brand_name = brand_name

        d = theme.create_native_dialog(
            parent,
            title=f"{brand_name} - Open-source licences",
            width=760,
            height=600,
            minsize=(640, 400),
            placement="parent-origin",
        )
        self.win = d
        d._pippal_notices_viewer = self
        d.transient(parent)
        d.bind("<Escape>", lambda _e: d.destroy())
        d.bind("<Alt-F4>", lambda _e: d.destroy())

        footer = ttk.Frame(d, style="TFrame", padding=(20, 10, 20, 16))
        footer.pack(fill="x", side="bottom")
        ttk.Button(footer, text="Close", command=d.destroy).pack(side="right")

        wrap = ttk.Frame(d, style="TFrame", padding=(20, 18, 20, 0))
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
        theme.show_native_dialog(d, parent, grab=True)



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
