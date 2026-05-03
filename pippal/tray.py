"""Tray icon image factory.

The icon is loaded from `assets/pippal_icon.png` and resized to 64×64.
While speaking we paint a small red badge in the lower-right. If the
asset is missing we fall back to a programmatically drawn flat circle
with a white "P", so the app still works in a stripped-down checkout."""

from __future__ import annotations

import sys

from PIL import Image, ImageDraw, ImageFont

from .paths import ASSET_ICON_PATH

# Pillow renamed Image.LANCZOS → Image.Resampling.LANCZOS in 9.1; keep
# both paths working without warnings.
_LANCZOS = getattr(Image, "Resampling", Image).LANCZOS

_icon_cache: dict[str, Image.Image] = {}


def make_tray_icon(speaking: bool) -> Image.Image:
    cache_key = "speaking" if speaking else "idle"
    cached = _icon_cache.get(cache_key)
    if cached is not None:
        return cached

    if ASSET_ICON_PATH.exists():
        try:
            base = (
                Image.open(ASSET_ICON_PATH)
                .convert("RGBA")
                .resize((64, 64), _LANCZOS)
            )
            if speaking:
                d = ImageDraw.Draw(base)
                d.ellipse(
                    (44, 44, 62, 62),
                    fill=(220, 80, 60),
                    outline=(255, 255, 255),
                    width=2,
                )
            _icon_cache[cache_key] = base
            return base
        except Exception as e:
            print(f"[icon] failed to load {ASSET_ICON_PATH}: {e}", file=sys.stderr)

    img = _draw_fallback_icon(speaking)
    _icon_cache[cache_key] = img
    return img


def _draw_fallback_icon(speaking: bool) -> Image.Image:
    img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    color = (220, 80, 60) if speaking else (109, 217, 184)
    d.ellipse((2, 2, 62, 62), fill=color)
    try:
        font = ImageFont.truetype("seguibl.ttf", 40)
    except Exception:
        try:
            font = ImageFont.truetype("arialbd.ttf", 40)
        except Exception:
            font = ImageFont.load_default()
    bbox = d.textbbox((0, 0), "P", font=font)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    d.text(
        ((64 - tw) / 2 - bbox[0], (64 - th) / 2 - bbox[1]),
        "P", font=font, fill="white",
    )
    return img
