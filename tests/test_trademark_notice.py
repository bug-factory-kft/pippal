"""Trademark notice guard: PipPal is marked ™, never ®.

The name is not a registered mark yet, so the shipped UI may only use ™.
The About card carries one trademark line per shipped language, and the
OS-facing names (config ``brand_name``, ``window.*.title``) stay plain so
window titles, the tray tooltip and the package identity keep the reserved
name.
"""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
I18N = ROOT / "webui" / "i18n"
TM = "™"
REGISTERED = "®"


def _catalogs() -> dict[str, dict]:
    return {
        path.stem: json.loads(path.read_text("utf-8"))
        for path in sorted(I18N.glob("*.json"))
        if not path.name.startswith("_") and path.stem != "en-XA"
    }


def test_about_trademark_line_in_every_shipped_language() -> None:
    catalogs = _catalogs()
    assert {"en", "hu", "de", "uk", "pt-BR", "zh-CN"} <= set(catalogs)
    for lang, catalog in catalogs.items():
        line = catalog.get("settings.about.trademark", "")
        assert f"PipPal{TM}" in line, f"{lang}: trademark line lacks PipPal™"
        assert "Bug Factory Kft." in line, f"{lang}: trademark line lacks owner"
    assert catalogs["en"]["settings.about.trademark"] == (
        "PipPal™ is a trademark of Bug Factory Kft."
    )
    assert catalogs["hu"]["settings.about.trademark"] == (
        "A PipPal™ a Bug Factory Kft. védjegye."
    )


def test_os_facing_names_stay_plain() -> None:
    from pippal.config import DEFAULT_CONFIG

    assert DEFAULT_CONFIG["brand_name"] == "PipPal"
    for lang, catalog in _catalogs().items():
        for key, value in catalog.items():
            if key.startswith("window.") and isinstance(value, str):
                assert TM not in value, f"{lang}:{key} is an OS window title"


def test_no_registered_mark_in_shipped_ui() -> None:
    webui = ROOT / "webui"
    for path in webui.rglob("*"):
        if path.suffix in {".json", ".js", ".html", ".css"}:
            text = path.read_text("utf-8")
            assert REGISTERED not in text, f"® found in {path.relative_to(ROOT)}"
