"""Piper voice catalogue and language-to-voice routing helpers."""

from __future__ import annotations

from pathlib import Path
from typing import TypedDict

from .paths import VOICES_DIR


class PiperVoice(TypedDict):
    id: str
    lang: str       # locale code like 'en_US'
    name: str       # speaker name in HF tree
    quality: str    # 'low' | 'medium' | 'high'
    label: str      # human-readable label for the Voice Manager


# Curated subset of voices on huggingface.co/rhasspy/piper-voices.
KNOWN_VOICES: list[PiperVoice] = [
    # English
    {"id": "en_US-ryan-high",                  "lang": "en_US", "name": "ryan",                "quality": "high",   "label": "Ryan — US male, very natural (recommended)"},
    {"id": "en_US-libritts_r-medium",          "lang": "en_US", "name": "libritts_r",          "quality": "medium", "label": "LibriTTS-R — US multi-speaker, very natural"},
    {"id": "en_US-hfc_female-medium",          "lang": "en_US", "name": "hfc_female",          "quality": "medium", "label": "HFC Female — US female, clear"},
    {"id": "en_US-hfc_male-medium",            "lang": "en_US", "name": "hfc_male",            "quality": "medium", "label": "HFC Male — US male, clear"},
    {"id": "en_US-amy-medium",                 "lang": "en_US", "name": "amy",                 "quality": "medium", "label": "Amy — US female, popular"},
    {"id": "en_US-lessac-high",                "lang": "en_US", "name": "lessac",              "quality": "high",   "label": "Lessac — US female, neutral"},
    {"id": "en_US-kathleen-low",               "lang": "en_US", "name": "kathleen",            "quality": "low",    "label": "Kathleen — US female (small/fast)"},
    {"id": "en_GB-alan-medium",                "lang": "en_GB", "name": "alan",                "quality": "medium", "label": "Alan — UK male"},
    {"id": "en_GB-northern_english_male-medium","lang": "en_GB","name": "northern_english_male","quality": "medium","label": "Northern English Male — UK"},
    {"id": "en_GB-jenny_dioco-medium",         "lang": "en_GB", "name": "jenny_dioco",         "quality": "medium", "label": "Jenny — UK female"},
    # Translation targets
    {"id": "hu_HU-anna-medium",                "lang": "hu_HU", "name": "anna",                "quality": "medium", "label": "Anna — Hungarian female (for translation)"},
    {"id": "de_DE-thorsten-medium",            "lang": "de_DE", "name": "thorsten",            "quality": "medium", "label": "Thorsten — German male"},
    {"id": "es_ES-davefx-medium",              "lang": "es_ES", "name": "davefx",              "quality": "medium", "label": "DaveFX — Spanish male"},
    {"id": "fr_FR-siwis-medium",               "lang": "fr_FR", "name": "siwis",               "quality": "medium", "label": "Siwis — French female"},
    {"id": "it_IT-paola-medium",               "lang": "it_IT", "name": "paola",               "quality": "medium", "label": "Paola — Italian female"},
    {"id": "nl_NL-mls_5809-low",               "lang": "nl_NL", "name": "mls_5809",            "quality": "low",    "label": "MLS — Dutch (small)"},
    {"id": "pl_PL-darkman-medium",             "lang": "pl_PL", "name": "darkman",             "quality": "medium", "label": "Darkman — Polish male"},
    {"id": "pt_PT-tugão-medium",               "lang": "pt_PT", "name": "tugão",               "quality": "medium", "label": "Tugão — Portuguese male"},
]


# Locale → human-readable language label, used by the Voice Manager
# filter dropdown. Falls back to the locale code for unknown values
# in `locale_name()` below.
LOCALE_TO_NAME: dict[str, str] = {
    "en_US": "English (US)",
    "en_GB": "English (UK)",
    "de_DE": "German",
    "es_ES": "Spanish",
    "es_MX": "Spanish (MX)",
    "fr_FR": "French",
    "it_IT": "Italian",
    "hu_HU": "Hungarian",
    "pl_PL": "Polish",
    "nl_NL": "Dutch",
    "pt_PT": "Portuguese",
    "pt_BR": "Portuguese (BR)",
    "cs_CZ": "Czech",
    "ro_RO": "Romanian",
    "sk_SK": "Slovak",
    "hr_HR": "Croatian",
    "tr_TR": "Turkish",
    "el_GR": "Greek",
    "ru_RU": "Russian",
    "uk_UA": "Ukrainian",
    "fi_FI": "Finnish",
    "no_NO": "Norwegian",
    "sv_SE": "Swedish",
    "da_DK": "Danish",
    "ja_JP": "Japanese",
    "zh_CN": "Chinese",
    "ko_KR": "Korean",
    "ar_JO": "Arabic",
    "fa_IR": "Persian",
    "ka_GE": "Georgian",
    "ca_ES": "Catalan",
    "lv_LV": "Latvian",
    "sl_SI": "Slovenian",
    "is_IS": "Icelandic",
    "cy_GB": "Welsh",
    "vi_VN": "Vietnamese",
    "fa_AF": "Dari",
    "lb_LU": "Luxembourgish",
    "mt_MT": "Maltese",
    "kk_KZ": "Kazakh",
    "uz_UZ": "Uzbek",
    "sw":    "Swahili",
}


def locale_name(code: str) -> str:
    """Human-readable label for a Piper locale code, falling back to
    the code itself when unknown — better to show 'xy_AB' than nothing."""
    return LOCALE_TO_NAME.get(code, code)


# Map human-readable language names → Piper locale codes (priority order).
LANG_TO_PIPER: dict[str, list[str]] = {
    "English":    ["en_US", "en_GB"],
    "Hungarian":  ["hu_HU"],
    "German":     ["de_DE"],
    "Spanish":    ["es_ES", "es_MX"],
    "French":     ["fr_FR"],
    "Italian":    ["it_IT"],
    "Polish":     ["pl_PL"],
    "Portuguese": ["pt_PT", "pt_BR"],
    "Czech":      ["cs_CZ"],
    "Romanian":   ["ro_RO"],
    "Slovak":     ["sk_SK"],
    "Croatian":   ["hr_HR"],
    "Turkish":    ["tr_TR"],
    "Greek":      ["el_GR"],
    "Dutch":      ["nl_NL"],
}


def voice_url_base(v: PiperVoice) -> str:
    base_lang = v["lang"].split("_")[0]
    return (
        "https://huggingface.co/rhasspy/piper-voices/resolve/main/"
        f"{base_lang}/{v['lang']}/{v['name']}/{v['quality']}/"
    )


def voice_filename(v: PiperVoice) -> str:
    return f"{v['id']}.onnx"


# Extension-supplied engines may use voices that don't fit the
# PiperVoice shape (no ``.onnx`` filename, no model card). They
# register their catalogues via
# ``plugins.register_engine_voice_options(<engine>, ...)``; the public
# package's Settings Voice card reads from that registry rather than
# hard-coding additional engines here.


def is_installed_voice(filename: str, voices_dir: Path | None = None) -> bool:
    """True when ``filename`` is a plain Piper .onnx file with sidecar."""
    name = (filename or "").strip()
    if not name.endswith(".onnx"):
        return False
    if Path(name).name != name:
        return False
    root = voices_dir or VOICES_DIR
    return (root / name).is_file() and (root / f"{name}.json").is_file()


def installed_voices(voices_dir: Path | None = None) -> list[str]:
    """Filenames of voices that have both .onnx and .onnx.json on disk."""
    root = voices_dir or VOICES_DIR
    if not root.exists():
        return []
    return sorted(
        p.name for p in root.glob("*.onnx")
        if is_installed_voice(p.name, voices_dir=root)
    )


def find_piper_voice_for_language(language: str) -> str | None:
    """Return an installed Piper voice filename matching the language,
    or None if nothing applicable is installed.

    Iterates the locale codes in priority order first, so e.g. an
    `en_US` voice wins over `en_GB` when both are installed."""
    installed = installed_voices()
    for code in LANG_TO_PIPER.get(language) or []:
        for v in installed:
            if v.startswith(f"{code}-"):
                return v
    return None
