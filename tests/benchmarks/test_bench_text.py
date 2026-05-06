"""Benchmarks for ``pippal.text_utils``.

These functions run on every speech chunk during a read, so any
regression here directly hits time-to-first-word and the karaoke
animation. We benchmark four representative text shapes:

- a one-line greeting (typical Read-Selection on a button label),
- a paragraph (typical Read-Selection on a chat message),
- a long article (Voice Manager → Read this as test),
- a single sentence longer than ``max_chunk_len`` (the
  hard-wrap branch of ``_wrap_long``).
"""

from __future__ import annotations

import pytest

from pippal.text_utils import (
    count_syllables,
    iter_word_spans,
    split_sentences,
    word_timing_weight,
)
from pippal.ui.overlay_paint import compute_word_layout

# Sample texts kept small enough to run fast in CI but representative
# of the real-world inputs PipPal sees.

_GREETING = "Hello, world! How are you today?"

_PARAGRAPH = (
    "PipPal is a tray-resident Windows app that reads any selected "
    "text aloud with a local neural TTS. Press a hotkey in any "
    "program — browser, PDF reader, Word, terminal — and a clean "
    "floating panel shows the sentence with a karaoke-style highlight."
)

# ~3 kB of mostly-English prose, ~10 sentences.
_ARTICLE = (_PARAGRAPH + "\n\n") * 6

# A single sentence longer than the default 400-char chunk cap, so the
# `_wrap_long` hard-wrap branch is exercised.
_LONG_SENTENCE = (
    "The cat sat on the mat and watched the rain fall outside the "
    "window for hours and hours, " * 10
).rstrip(", ") + "."


pytestmark = pytest.mark.benchmark(group="text_utils")


def test_split_sentences_greeting(benchmark):
    benchmark(split_sentences, _GREETING)


def test_split_sentences_paragraph(benchmark):
    benchmark(split_sentences, _PARAGRAPH)


def test_split_sentences_article(benchmark):
    benchmark(split_sentences, _ARTICLE)


def test_split_sentences_long_single(benchmark):
    """Hits the `_wrap_long` hard-wrap branch."""
    benchmark(split_sentences, _LONG_SENTENCE)


def test_count_syllables(benchmark):
    benchmark(count_syllables, "ridiculously")


def test_word_timing_weight(benchmark):
    benchmark(word_timing_weight, "sentence,")


def test_iter_word_spans_paragraph(benchmark):
    # Materialise the iterator into a list — the iterator itself is
    # lazy, so without consuming it we'd time the regex compile only.
    benchmark(lambda: list(iter_word_spans(_PARAGRAPH)))


def test_compute_word_layout(benchmark):
    """Karaoke layout for a paragraph at typical TTS chunk duration.
    Uses a stub font that returns a fixed pixel width per character so
    the benchmark doesn't depend on Tk being initialised."""

    class _StubFont:
        def measure(self, s: str) -> int:
            return 8 * len(s)

    benchmark(
        compute_word_layout,
        _PARAGRAPH, 12.0, _StubFont(), 760, 32, 4,
    )
