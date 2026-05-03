from __future__ import annotations

import re

from pippal.ui.theme import UI


class TestUIPalette:
    def test_required_keys(self):
        for key in ("bg", "bg_card", "bg_input", "border", "text",
                    "text_dim", "text_mute", "accent", "danger"):
            assert key in UI, f"palette missing {key}"

    def test_all_values_are_hex_triplets(self):
        hex_re = re.compile(r"^#[0-9a-fA-F]{6}$")
        for key, val in UI.items():
            assert hex_re.match(val), f"{key} = {val!r} is not a 6-digit #rrggbb"
