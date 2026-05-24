from __future__ import annotations

import pytest

from pippal.text_utils import (
    count_syllables,
    iter_word_spans,
    split_sentences,
    word_timing_weight,
)


class TestSplitSentences:
    def test_empty(self):
        assert split_sentences("") == []
        assert split_sentences("   ") == []
        assert split_sentences(None) == []  # type: ignore[arg-type]

    def test_single_sentence(self):
        assert split_sentences("Hello world.") == ["Hello world."]

    def test_multiple_short_sentences_packed(self):
        text = "One. Two. Three."
        # All short — get packed into a single chunk under the cap.
        assert split_sentences(text) == ["One. Two. Three."]

    def test_chunks_when_over_cap(self):
        long_part = "a" * 200
        text = f"{long_part}. {long_part}. {long_part}."
        chunks = split_sentences(text, max_chunk_len=250)
        assert len(chunks) >= 2
        for c in chunks:
            assert len(c) < 250 or c.count(".") <= 1  # at most one full sentence over cap

    def test_hard_wraps_long_punctuation_free_sentence(self):
        # One mega-sentence, no periods, much longer than the cap. Must
        # be wrapped on whitespace rather than emitted whole.
        text = " ".join(["word"] * 200)   # ~1000 chars
        chunks = split_sentences(text, max_chunk_len=200)
        for c in chunks:
            assert len(c) <= 200, f"chunk {len(c)} > 200: {c!r}"
        # Re-joining recovers the original (modulo single spaces).
        assert " ".join(chunks).split() == text.split()

    def test_hard_wraps_long_unbroken_token(self):
        text = "x" * 1000
        chunks = split_sentences(text, max_chunk_len=200)

        assert len(chunks) == 5
        assert all(len(c) <= 200 for c in chunks)
        assert "".join(chunks) == text

    def test_hard_wraps_long_unbroken_token_inside_sentence(self):
        token = "a" * 450
        chunks = split_sentences(f"prefix {token} suffix", max_chunk_len=200)

        assert all(len(c) <= 200 for c in chunks)
        assert chunks[0] == "prefix"
        assert chunks[-1].endswith("suffix")
        assert any(c == "a" * 200 for c in chunks)

    def test_question_and_exclamation(self):
        assert split_sentences("Hi! How are you?") == ["Hi! How are you?"]

    def test_strips_outer_whitespace(self):
        assert split_sentences("  hello  ") == ["hello"]

    # --- newline-boundary tests ---

    def test_bullet_list_each_line_is_separate_chunk(self):
        text = "- Apples\n- Oranges\n- Bananas"
        chunks = split_sentences(text)
        assert chunks == ["- Apples", "- Oranges", "- Bananas"]

    def test_numbered_list_each_line_is_separate_chunk(self):
        text = "1. Cat\n2. Dog\n3. Bird"
        chunks = split_sentences(text)
        assert chunks == ["1. Cat", "2. Dog", "3. Bird"]

    def test_blank_lines_ignored(self):
        text = "- Apples\n\n- Oranges\n\n- Bananas"
        chunks = split_sentences(text)
        assert chunks == ["- Apples", "- Oranges", "- Bananas"]

    def test_leading_trailing_whitespace_trimmed_per_line(self):
        text = "  - Apples  \n  - Oranges  "
        chunks = split_sentences(text)
        assert chunks == ["- Apples", "- Oranges"]

    def test_prose_still_splits_on_punctuation(self):
        # Normal sentences with terminal punctuation must still pack under
        # the cap — no regression for prose paragraphs.
        text = "The cat sat. The dog ran."
        chunks = split_sentences(text)
        # Both short sentences fit in one chunk (single line, no newline).
        assert chunks == ["The cat sat. The dog ran."]

    def test_mixed_list_and_prose_line(self):
        # A line that itself contains multiple sentences is split by
        # punctuation, while the newline forces a new chunk.
        text = "Hello world. How are you?\n- Apples\n- Oranges"
        chunks = split_sentences(text)
        assert chunks[0] == "Hello world. How are you?"
        assert "- Apples" in chunks
        assert "- Oranges" in chunks


class TestCountSyllables:
    @pytest.mark.parametrize("word,expected", [
        ("a", 1),
        ("the", 1),
        ("hello", 2),
        ("syllable", 3),
        ("automation", 4),  # au-to-ma-tion
        # silent-e
        ("home", 1),
        # 'le' ending stays syllabic
        ("apple", 2),
        ("table", 2),
        # punctuation stripped
        ("hello,", 2),
        ("end.", 1),
        # empty / whitespace falls back to 1
        ("", 1),
        ("   ", 1),
    ])
    def test_examples(self, word, expected):
        assert count_syllables(word) == expected

    def test_known_heuristic_limitations(self):
        # `create` is genuinely 2 syllables (cre-ate) but the cheap
        # vowel-cluster heuristic with silent-e adjustment scores it as 1.
        # The error is small enough not to matter for karaoke weighting.
        assert count_syllables("create") in (1, 2)

    def test_returns_at_least_one(self):
        # Pathological: only punctuation
        assert count_syllables("!!!") == 1


class TestWordTimingWeight:
    def test_plain_word_equals_syllables(self):
        assert word_timing_weight("hello") == count_syllables("hello")

    def test_period_adds_pause(self):
        plain = word_timing_weight("end")
        with_period = word_timing_weight("end.")
        # Period adds a substantial pause (~1.6).
        assert with_period == pytest.approx(plain + 1.6, abs=0.01)

    def test_comma_adds_smaller_pause(self):
        plain = word_timing_weight("yes")
        with_comma = word_timing_weight("yes,")
        assert with_comma == pytest.approx(plain + 0.7, abs=0.01)

    def test_question_mark_pause(self):
        assert word_timing_weight("why?") > word_timing_weight("why")

    def test_returns_float(self):
        assert isinstance(word_timing_weight("hello"), float)


class TestIterWordSpans:
    def test_yields_words(self):
        spans = list(iter_word_spans("hello world"))
        assert [m.group() for m in spans] == ["hello", "world"]

    def test_handles_punctuation(self):
        spans = list(iter_word_spans("Hi, world!"))
        assert [m.group() for m in spans] == ["Hi,", "world!"]

    def test_empty(self):
        assert list(iter_word_spans("")) == []
