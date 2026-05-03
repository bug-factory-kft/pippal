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
            base = _load_and_fit_icon()
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


_ICON_OVERSCALE = 1.20  # >1 = character fills more of the 64×64 cell


def _load_and_fit_icon() -> Image.Image:
    """Crop the asset to its non-transparent content (so generous
    print-margins don't shrink the visible character), scale so the
    longer dimension is `64 * _ICON_OVERSCALE`, and paste centred
    onto a 64×64 transparent canvas. The overscale lets the character
    occupy more of the cell; only the empty alpha around the bbox
    gets clipped."""
    img = Image.open(ASSET_ICON_PATH).convert("RGBA")
    bbox = img.getbbox()
    if bbox is not None:
        img = img.crop(bbox)
    w, h = img.size
    target_long = int(64 * _ICON_OVERSCALE)
    scale = target_long / max(w, h)
    new_w = max(1, round(w * scale))
    new_h = max(1, round(h * scale))
    img = img.resize((new_w, new_h), _LANCZOS)
    canvas = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    canvas.paste(img, ((64 - new_w) // 2, (64 - new_h) // 2), img)
    return canvas


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
