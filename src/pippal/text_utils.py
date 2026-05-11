"""Pure text helpers: sentence splitting and karaoke timing weights."""

from __future__ import annotations

import re
from collections.abc import Iterable

_PUNCT_SENTENCE = re.compile(r"(?<=[.!?])\s+")
_WORD_RE = re.compile(r"\S+")
_VOWELS = "aeiouyáéíóöőúüű"
_TRIM_CHARS = "'\"-.,;:!?()[]{}<>/«»“”…"


def split_sentences(text: str, max_chunk_len: int = 400) -> list[str]:
    """Split text into chunks of up to ~`max_chunk_len` characters along
    sentence boundaries. Aimed at TTS engines that want medium-length
    inputs for natural prosody. A single sentence longer than
    `max_chunk_len` is hard-wrapped on whitespace as a fallback, with
    oversized unbroken tokens split directly so a paragraph-shaped
    one-sentence input never exceeds the cap."""
    text = (text or "").strip()
    if not text:
        return []

    parts = _PUNCT_SENTENCE.split(text)
    chunks: list[str] = []
    buf = ""
    for part in parts:
        if not part:
            continue
        for sub in _wrap_long(part, max_chunk_len):
            if not buf:
                buf = sub
            elif len(buf) + 1 + len(sub) <= max_chunk_len:
                buf = f"{buf} {sub}"
            else:
                chunks.append(buf)
                buf = sub
    if buf:
        chunks.append(buf)
    return chunks


def _wrap_long(sentence: str, max_len: int) -> list[str]:
    """Hard-wrap an over-long sentence.

    Prefer whitespace boundaries, but split a single oversized token
    directly so URLs/base64/minified identifiers cannot exceed the cap.
    """
    sentence = sentence.strip()
    max_len = max(1, int(max_len))
    if len(sentence) <= max_len:
        return [sentence]

    words = sentence.split()
    out: list[str] = []
    buf = ""
    for w in words:
        if len(w) > max_len:
            if buf:
                out.append(buf)
                buf = ""
            out.extend(_split_unbroken_token(w, max_len))
        elif not buf:
            buf = w
        elif len(buf) + 1 + len(w) <= max_len:
            buf = f"{buf} {w}"
        else:
            out.append(buf)
            buf = w
    if buf:
        out.append(buf)
    return out


def _split_unbroken_token(token: str, max_len: int) -> list[str]:
    return [token[i:i + max_len] for i in range(0, len(token), max_len)]


def count_syllables(word: str) -> int:
    """Heuristic syllable count, biased to English but tolerable for
    other Latin-script languages including Hungarian (extra vowels are
    included). Returns at least 1."""
    w = (word or "").lower().strip(_TRIM_CHARS)
    if not w:
        return 1
    count = 0
    prev_vowel = False
    for ch in w:
        is_vowel = ch in _VOWELS
        if is_vowel and not prev_vowel:
            count += 1
        prev_vowel = is_vowel
    # Drop a silent final 'e' (rough), keeping 'le' endings as syllabic.
    if w.endswith("e") and count > 1 and not w.endswith("le"):
        count -= 1
    return max(1, count)


def word_timing_weight(token: str) -> float:
    """Per-word weight used to apportion the chunk's duration across
    words for karaoke. Trailing punctuation gets a small pause bonus."""
    syl = count_syllables(token)
    if token.endswith((".", "!", "?", "…")):
        return syl + 1.6
    if token.endswith((",", ";", ":", "—", "–")):
        return syl + 0.7
    return float(syl)


def iter_word_spans(text: str) -> Iterable[re.Match[str]]:
    """Yield re.Match objects for each non-whitespace token in `text`."""
    return _WORD_RE.finditer(text or "")
