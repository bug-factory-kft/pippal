"""Per-card builders for the Settings window.

Pulled out of `settings_window.py` so each card sits at one screen and
the SettingsWindow class itself can stay focused on lifecycle (open,
close, save, listing). Every builder receives the SettingsWindow
instance (`sw`) and the card-list parent frame (`body`); it adds widgets
to `body` and registers any `tk.Variable`s it owns into `sw.vars` for
the SettingsWindow's `_save` to read."""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import TYPE_CHECKING

from .. import plugins
from ..config import DEFAULT_CONFIG
from .theme import make_card

if TYPE_CHECKING:  # pragma: no cover
    from .settings_window import SettingsWindow


def build_voice_card(sw: SettingsWindow, body: ttk.Frame) -> None:
    outer, card = make_card(body, "Voice")
    outer.pack(fill="x", pady=(0, 12))

    erow = ttk.Frame(card, style="Card.TFrame")
    erow.pack(fill="x")
    ttk.Label(erow, text="Engine", style="Card.TLabel",
              width=14, anchor="w").pack(side="left")
    # Engine combo lists every TTS backend that any plugin has
    # registered. The core pippal registers `piper`; pippal_pro adds
    # `kokoro`. A future ElevenLabs or Edge TTS plugin would slot in
    # here without touching this card.
    available_engines = sorted(plugins.engines().keys()) or ["piper"]
    # If the saved engine isn't registered (e.g. user picked Kokoro
    # under Pro, then dropped to the public package), surface "piper" in the form
    # rather than the unregistered name. Codex' "Unavailable action"
    # principle: don't destroy the persisted value (config.json keeps
    # 'kokoro' so a future Pro reinstall picks it up), but don't fake
    # presence in the UI either.
    saved_engine = (sw.config.get("engine") or "piper").lower()
    initial_engine = saved_engine if saved_engine in available_engines else available_engines[0]
    sw.vars["engine"] = tk.StringVar(value=initial_engine)
    sw.engine_combo = ttk.Combobox(erow, textvariable=sw.vars["engine"],
                                   values=available_engines,
                                   state="readonly", width=14)
    sw.engine_combo.pack(side="left")
    sw.engine_combo.bind("<<ComboboxSelected>>",
                          lambda _e: sw._on_engine_change())

    # Optional Kokoro language filter — packed into the card only
    # when engine == 'kokoro' (see settings_window._on_engine_change).
    # 54 voices in the dropdown is too many to scan otherwise; the
    # filter trims the voice combo below to one language at a time.
    sw.kokoro_lang_row = ttk.Frame(card, style="Card.TFrame")
    ttk.Label(sw.kokoro_lang_row, text="Language", style="Card.TLabel",
              width=14, anchor="w").pack(side="left")
    sw.vars["kokoro_lang"] = tk.StringVar(value="All")
    sw.kokoro_lang_combo = ttk.Combobox(
        sw.kokoro_lang_row, textvariable=sw.vars["kokoro_lang"],
        state="readonly",
    )
    sw.kokoro_lang_combo.pack(side="left", fill="x", expand=True)
    sw.kokoro_lang_combo.bind(
        "<<ComboboxSelected>>",
        lambda _e: sw._on_engine_change(),
    )

    # Stored on `sw` so `_on_engine_change` can pack `kokoro_lang_row`
    # *before* the voice row (i.e. right under Engine), instead of
    # appending it at the bottom of the card.
    sw.voice_row = ttk.Frame(card, style="Card.TFrame")
    vrow = sw.voice_row
    vrow.pack(fill="x", pady=(10, 0))
    ttk.Label(vrow, text="Voice", style="Card.TLabel",
              width=14, anchor="w").pack(side="left")
    sw.vars["voice_display"] = tk.StringVar()
    sw.voice_combo = ttk.Combobox(vrow, textvariable=sw.vars["voice_display"],
                                  state="readonly")
    sw.voice_combo.pack(side="left", fill="x", expand=True)
    sw.manage_btn = ttk.Button(vrow, text="Manage…", style="Card.TButton",
                                command=sw._open_voice_manager)
    sw.manage_btn.pack(side="left", padx=(10, 0))

    sw.vars["voice"] = tk.StringVar(
        value=sw.config.get("voice", DEFAULT_CONFIG["voice"]))
    sw.vars["kokoro_voice"] = tk.StringVar(
        value=sw.config.get("kokoro_voice", DEFAULT_CONFIG["kokoro_voice"]))

    sw.engine_hint = ttk.Label(card, text="", style="CardHint.TLabel",
                                wraplength=480, justify="left")
    sw.engine_hint.pack(anchor="w", pady=(8, 0))

    sw.kokoro_install_btn = ttk.Button(
        card, text="Install Kokoro engine (~340 MB)…",
        style="Card.TButton",
        command=sw._install_kokoro,
    )
    sw._on_engine_change()


def build_speech_card(sw: SettingsWindow, body: ttk.Frame) -> None:
    outer, card = make_card(body, "Speech")
    outer.pack(fill="x", pady=(0, 12))

    srow = ttk.Frame(card, style="Card.TFrame")
    srow.pack(fill="x")
    ttk.Label(srow, text="Speed", style="Card.TLabel",
              width=14, anchor="w").pack(side="left")
    ls = float(sw.config.get("length_scale", 1.0))
    sw.vars["speed"] = tk.DoubleVar(value=round(1.0 / ls, 2) if ls else 1.0)
    sw.speed_label = ttk.Label(srow, text="", style="Card.TLabel",
                                width=6, anchor="e")
    ttk.Scale(srow, from_=0.6, to=1.7, variable=sw.vars["speed"],
              command=lambda _v: sw._update_speed_label()).pack(
        side="left", fill="x", expand=True, padx=(8, 8))
    sw.speed_label.pack(side="left")
    sw._update_speed_label()

    vrow = ttk.Frame(card, style="Card.TFrame")
    vrow.pack(fill="x", pady=(10, 0))
    ttk.Label(vrow, text="Variation", style="Card.TLabel",
              width=14, anchor="w").pack(side="left")
    sw.vars["noise_scale"] = tk.DoubleVar(
        value=float(sw.config.get("noise_scale", 0.667)))
    sw.var_label = ttk.Label(vrow, text="", style="Card.TLabel",
                              width=6, anchor="e")
    ttk.Scale(vrow, from_=0.3, to=1.0, variable=sw.vars["noise_scale"],
              command=lambda _v: sw._update_var_label()).pack(
        side="left", fill="x", expand=True, padx=(8, 8))
    sw.var_label.pack(side="left")
    sw._update_var_label()

    ttk.Label(card,
              text="Speed: 0.6× clearer · 1.0× normal · 1.7× faster.   "
                   "Variation: livelier intonation at higher values.",
              style="CardHint.TLabel", wraplength=500, justify="left",
              ).pack(anchor="w", pady=(10, 0))


def build_hotkeys_card(sw: SettingsWindow, body: ttk.Frame) -> None:
    outer, card = make_card(body, "Hotkeys")
    outer.pack(fill="x", pady=(0, 12))
    # Label width is sized for the longest registered hotkey label so
    # the entries line up vertically and no label gets clipped. Falls
    # back to 18 (the previous fixed width) when there are no actions.
    actions = list(plugins.hotkey_actions())
    label_w = max((len(label) for _a, _k, label, _d in actions), default=18) + 2
    for i, (_action_id, key, label_text, default) in enumerate(actions):
        row = ttk.Frame(card, style="Card.TFrame")
        row.pack(fill="x", pady=(0 if i == 0 else 8, 0))
        ttk.Label(row, text=label_text, style="Card.TLabel",
                  width=label_w, anchor="w").pack(side="left")
        sw.vars[key] = tk.StringVar(
            value=sw.config.get(key, default))
        ttk.Entry(row, textvariable=sw.vars[key]).pack(
            side="left", fill="x", expand=True)

    ttk.Label(card,
              text="Format: windows+shift+r · ctrl+alt+space · alt+shift+f1 …  "
                   "Captured combos are suppressed (other apps won't also see them).",
              style="CardHint.TLabel", wraplength=480, justify="left",
              ).pack(anchor="w", pady=(10, 0))


def build_panel_card(sw: SettingsWindow, body: ttk.Frame) -> None:
    outer, card = make_card(body, "Reader panel")
    outer.pack(fill="x", pady=(0, 12))

    sw.vars["show_overlay"] = tk.BooleanVar(
        value=bool(sw.config.get("show_overlay", True)))
    ttk.Checkbutton(card, text="Show panel while reading",
                    variable=sw.vars["show_overlay"]).pack(anchor="w")

    sw.vars["show_text_in_overlay"] = tk.BooleanVar(
        value=bool(sw.config.get("show_text_in_overlay", True)))
    ttk.Checkbutton(card, text="Show text with karaoke highlight",
                    variable=sw.vars["show_text_in_overlay"]).pack(anchor="w", pady=(4, 0))

    _spinbox_row(sw, card, "Auto-hide delay", "auto_hide_ms",
                  default=DEFAULT_CONFIG["auto_hide_ms"],
                  unit="ms", from_=300, to=8000, increment=100, pady=(12, 0))
    _spinbox_row(sw, card, "Distance from taskbar", "overlay_y_offset",
                  default=DEFAULT_CONFIG["overlay_y_offset"],
                  unit="px", from_=20, to=600, increment=10, pady=(8, 0))
    _spinbox_row(sw, card, "Karaoke offset", "karaoke_offset_ms",
                  default=DEFAULT_CONFIG["karaoke_offset_ms"],
                  unit="ms (positive = highlight waits, negative = highlight leads)",
                  from_=-300, to=600, increment=20, pady=(8, 0))


def _spinbox_row(
    sw: SettingsWindow,
    card: ttk.Frame,
    label: str,
    key: str,
    default: int,
    unit: str,
    *,
    from_: int,
    to: int,
    increment: int,
    pady: tuple[int, int],
) -> None:
    """Helper for the three identical labelled-spinbox rows in the
    Reader panel card."""
    row = ttk.Frame(card, style="Card.TFrame")
    row.pack(fill="x", pady=pady)
    ttk.Label(row, text=label, style="Card.TLabel",
              width=18, anchor="w").pack(side="left")
    sw.vars[key] = tk.IntVar(value=int(sw.config.get(key, default)))
    ttk.Spinbox(row, from_=from_, to=to, increment=increment, width=8,
                textvariable=sw.vars[key]).pack(side="left")
    ttk.Label(row, text=unit, style="CardHint.TLabel").pack(
        side="left", padx=(6, 0))


def build_integration_card(sw: SettingsWindow, body: ttk.Frame) -> None:
    outer, card = make_card(body, "Windows integration")
    outer.pack(fill="x", pady=(0, 12))
    sw.ctx_status = ttk.Label(card, text="", style="Card.TLabel")
    sw.ctx_status.pack(anchor="w")
    ttk.Label(
        card,
        text="Adds a 'Read with PipPal' entry to the right-click menu of "
             ".txt and .md files in File Explorer (current user only).",
        style="CardHint.TLabel", wraplength=480, justify="left",
    ).pack(anchor="w", pady=(2, 8))
    ctx_row = ttk.Frame(card, style="Card.TFrame")
    ctx_row.pack(fill="x")
    ttk.Button(ctx_row, text="Install", style="Card.TButton",
               command=sw._install_ctx).pack(side="left")
    ttk.Button(ctx_row, text="Remove", style="Danger.TButton",
               command=sw._remove_ctx).pack(side="left", padx=(8, 0))
    sw._refresh_ctx_status()


def build_about_card(sw: SettingsWindow, body: ttk.Frame) -> None:
    import webbrowser

    from .. import __version__
    from .theme import UI
    brand = sw.config.get("brand_name", "PipPal")
    outer, card = make_card(body, "About")
    outer.pack(fill="x", pady=(0, 16))
    ttk.Label(
        card, text=f"{brand} {__version__}",
        style="Card.TLabel", font=("Segoe UI Semibold", 10),
    ).pack(anchor="w")
    ttk.Label(
        card, text="Your little offline reading buddy.",
        style="CardHint.TLabel",
    ).pack(anchor="w", pady=(2, 0))
    ttk.Label(
        card, text="© 2026 Bug Factory Kft.  ·  Offline-first by design.",
        style="CardHint.TLabel",
    ).pack(anchor="w", pady=(8, 0))

    # Clickable links — public site first (Bug Factory's user-facing
    # landing page), then GitHub for source / licence / privacy /
    # terms. Microsoft Store paid users still see them so they have a
    # way to read the licence and terms even without the repo.
    link_row = ttk.Frame(card, style="Card.TFrame")
    link_row.pack(anchor="w", pady=(10, 0))

    def _link(parent: ttk.Frame, text: str, url: str) -> None:
        lbl = tk.Label(
            parent, text=text, bg=UI["bg_card"], fg=UI["accent"],
            cursor="hand2", font=("Segoe UI", 9, "underline"),
            borderwidth=0, padx=0, pady=0,
        )
        lbl.pack(side="left", padx=(0, 16))
        lbl.bind("<Button-1>", lambda _e: webbrowser.open(url))

    _link(link_row, "Website",
          "https://pippal.bugfactory.hu")
    _link(link_row, "GitHub",
          "https://github.com/bug-factory-kft/pippal")
    _link(link_row, "Licence (MIT)",
          "https://github.com/bug-factory-kft/pippal/blob/main/LICENSE.md")
    _link(link_row, "Privacy",
          "https://github.com/bug-factory-kft/pippal/blob/main/docs/PRIVACY.md")
    _link(link_row, "Terms",
          "https://github.com/bug-factory-kft/pippal/blob/main/docs/TERMS.md")
