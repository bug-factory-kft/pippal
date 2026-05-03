"""Dark Tk/ttk theme: a single colour palette and one configuration
function applied to every Toplevel, plus a `make_card` helper."""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk

UI: dict[str, str] = {
    "bg":         "#13151c",
    "bg_card":    "#1a1d28",
    "bg_input":   "#1f2230",
    "bg_hover":   "#262a3a",
    "border":     "#262a3a",
    "border_lt":  "#2f3447",
    "text":       "#e8ebfa",
    "text_dim":   "#8a90a8",
    "text_mute":  "#6c7088",
    "accent":     "#6dd9b8",
    "accent_dk":  "#0c1e1a",
    "accent_lt":  "#82e6c5",
    "danger":     "#c14d4d",
}


def apply_dark_theme(toplevel: tk.Misc) -> None:
    """Configure ttk styles for a dark theme on the given Toplevel/Tk."""
    toplevel.configure(bg=UI["bg"])
    style = ttk.Style(toplevel)
    try:
        style.theme_use("clam")
    except Exception:
        pass

    # Root + frames
    style.configure(".", background=UI["bg"], foreground=UI["text"],
                    font=("Segoe UI", 10), borderwidth=0)
    style.configure("TFrame", background=UI["bg"])
    style.configure("Card.TFrame", background=UI["bg_card"], relief="flat")
    style.configure("Header.TFrame", background=UI["bg"])

    # Labels
    style.configure("TLabel", background=UI["bg"], foreground=UI["text"])
    style.configure("Card.TLabel", background=UI["bg_card"], foreground=UI["text"])
    style.configure("Title.TLabel", background=UI["bg"], foreground=UI["text"],
                    font=("Segoe UI Semibold", 16))
    style.configure("Sub.TLabel", background=UI["bg"], foreground=UI["text_dim"],
                    font=("Segoe UI", 9))
    style.configure("Section.TLabel", background=UI["bg_card"], foreground=UI["text_dim"],
                    font=("Segoe UI Semibold", 9))
    style.configure("CardHint.TLabel", background=UI["bg_card"], foreground=UI["text_mute"],
                    font=("Segoe UI", 8))

    # Buttons
    style.configure("TButton", background=UI["bg_input"], foreground=UI["text"],
                    bordercolor=UI["border_lt"], lightcolor=UI["bg_input"],
                    darkcolor=UI["bg_input"], focusthickness=0, padding=(14, 7),
                    font=("Segoe UI", 9))
    style.map("TButton",
              background=[("active", UI["bg_hover"]), ("pressed", UI["bg_hover"])],
              bordercolor=[("active", UI["accent"])])

    style.configure("Primary.TButton", background=UI["accent"], foreground=UI["accent_dk"],
                    bordercolor=UI["accent"], lightcolor=UI["accent"],
                    darkcolor=UI["accent"], focusthickness=0, padding=(16, 7),
                    font=("Segoe UI Semibold", 9))
    style.map("Primary.TButton",
              background=[("active", UI["accent_lt"]), ("pressed", UI["accent_lt"])])

    style.configure("Card.TButton", background=UI["bg_input"], foreground=UI["text"],
                    bordercolor=UI["border_lt"], lightcolor=UI["bg_input"],
                    darkcolor=UI["bg_input"], focusthickness=0, padding=(12, 6),
                    font=("Segoe UI", 9))
    style.map("Card.TButton",
              background=[("active", UI["bg_hover"]), ("pressed", UI["bg_hover"])],
              bordercolor=[("active", UI["accent"])])

    style.configure("Danger.TButton", background=UI["bg_input"], foreground="#e8b0b0",
                    bordercolor="#5a2a2a", lightcolor=UI["bg_input"],
                    darkcolor=UI["bg_input"], focusthickness=0, padding=(12, 6))
    style.map("Danger.TButton",
              background=[("active", "#3a2030")],
              bordercolor=[("active", UI["danger"])])

    # Entries
    style.configure("TEntry", fieldbackground=UI["bg_input"], foreground=UI["text"],
                    bordercolor=UI["border_lt"], lightcolor=UI["border_lt"],
                    darkcolor=UI["border_lt"], insertcolor=UI["text"], padding=6)
    style.map("TEntry",
              bordercolor=[("focus", UI["accent"])],
              lightcolor=[("focus", UI["accent"])],
              darkcolor=[("focus", UI["accent"])])

    # Combobox
    style.configure("TCombobox", fieldbackground=UI["bg_input"], foreground=UI["text"],
                    background=UI["bg_input"], bordercolor=UI["border_lt"],
                    arrowcolor=UI["text_dim"], padding=4, lightcolor=UI["bg_input"],
                    darkcolor=UI["bg_input"])
    style.map("TCombobox",
              fieldbackground=[("readonly", UI["bg_input"])],
              foreground=[("readonly", UI["text"])],
              selectbackground=[("readonly", UI["bg_input"])],
              selectforeground=[("readonly", UI["text"])],
              bordercolor=[("focus", UI["accent"])])

    # Spinbox
    style.configure("TSpinbox", fieldbackground=UI["bg_input"], foreground=UI["text"],
                    bordercolor=UI["border_lt"], arrowcolor=UI["text_dim"],
                    padding=4, lightcolor=UI["bg_input"], darkcolor=UI["bg_input"])
    style.map("TSpinbox", bordercolor=[("focus", UI["accent"])])

    # Checkbutton
    style.configure("TCheckbutton", background=UI["bg_card"], foreground=UI["text"],
                    indicatorbackground=UI["bg_input"], focusthickness=0,
                    indicatorforeground=UI["accent"], padding=4)
    style.map("TCheckbutton",
              background=[("active", UI["bg_card"])],
              indicatorbackground=[("selected", UI["accent"])])

    # Scale
    style.configure("Horizontal.TScale", background=UI["bg_card"],
                    troughcolor=UI["bg_input"], bordercolor=UI["border_lt"],
                    lightcolor=UI["accent"], darkcolor=UI["accent"])

    # Scrollbar
    style.configure("Vertical.TScrollbar", background=UI["bg_input"],
                    troughcolor=UI["bg"], bordercolor=UI["bg"],
                    arrowcolor=UI["text_dim"], lightcolor=UI["bg_input"],
                    darkcolor=UI["bg_input"])

    # Combobox dropdown listbox (it's not a ttk widget — use option_add).
    toplevel.option_add("*TCombobox*Listbox.background", UI["bg_input"])
    toplevel.option_add("*TCombobox*Listbox.foreground", UI["text"])
    toplevel.option_add("*TCombobox*Listbox.selectBackground", UI["accent"])
    toplevel.option_add("*TCombobox*Listbox.selectForeground", UI["accent_dk"])
    toplevel.option_add("*TCombobox*Listbox.borderWidth", 0)
    toplevel.option_add("*TCombobox*Listbox.relief", "flat")
    toplevel.option_add("*TCombobox*Listbox.font", "Segoe\\ UI 10")


def make_card(parent: tk.Misc, title: str | None = None) -> tuple[ttk.Frame, ttk.Frame]:
    """Create a card frame with an optional section title.

    Returns ``(outer, card)``: pack ``outer`` into the parent layout, put
    your widgets inside ``card`` with ``Card.*`` ttk styles."""
    outer = ttk.Frame(parent, style="TFrame")
    card = ttk.Frame(outer, style="Card.TFrame", padding=(20, 16, 20, 16))
    card.pack(fill="x")
    if title:
        ttk.Label(card, text=title.upper(), style="Section.TLabel").pack(
            anchor="w", pady=(0, 12)
        )
    return outer, card
