"""Real-object resume-clock regression test for the pause/resume race.

Prior pause work asserted against MagicMock overlays and therefore never
exercised the real ``WebOverlay`` clock. This test drives the REAL
``WebOverlay`` plus the REAL resume sequence the playback loop performs
on resume, with a controllable clock so ``elapsed`` is deterministic.

Bug under test: pause then play restarts the chunk from the beginning.
On resume both ``engine.pause_toggle`` -> ``set_paused(False)`` AND the
playback loop's ``start_chunk(offset_s=karaoke_offset + elapsed_s)`` try
to rebase ``_chunk_start``; the second one wins and the snapshot
``elapsed`` collapses to ~0, so the karaoke highlight jumps back to
word 0 even though audio resumed mid-chunk.

The assertions below MUST fail on current main (elapsed resets to ~0)
and pass once a single source of truth for resume-elapsed is used.
"""

from __future__ import annotations

from pippal.web_ui.overlay_state import WebOverlay

# A multi-word chunk long enough that ~4s in lands on a non-zero word.
CHUNK_TEXT = "alpha bravo charlie delta echo foxtrot golf hotel india juliet"
CHUNK_DURATION = 10.0
KARAOKE_OFFSET_S = 0.15  # mirrors a typical karaoke_offset_ms = 150


class FakeClock:
    """Deterministic monotonic-ish clock the overlay reads instead of
    ``time.time``. Tests advance it explicitly."""

    def __init__(self, t: float = 1000.0) -> None:
        self.t = t

    def __call__(self) -> float:
        return self.t

    def advance(self, dt: float) -> None:
        self.t += dt


def _karaoke_word_index(snapshot: dict) -> int:
    """Derive the karaoke 'current word' index from a snapshot exactly the
    way the browser does: the last word whose start <= elapsed."""
    elapsed = snapshot["elapsed"]
    cur = 0
    for i, w in enumerate(snapshot["words"]):
        if w["ts"] <= elapsed:
            cur = i
    return cur


def _resume_start_chunk_kwargs(elapsed_at_resume: float) -> dict:
    """Build the ``start_chunk`` keyword arguments the playback loop uses
    on resume, against whatever signature the installed source exposes.

    - main (buggy): no ``resume_elapsed_s``; the loop folds the elapsed
      into ``offset_s = karaoke_offset + elapsed`` -> double reset.
    - fixed: ``resume_elapsed_s`` carries the audio tail's elapsed as the
      single source of truth; ``offset_s`` is just the latency comp.

    This keeps the test runnable RED-on-main and GREEN-after-fix without a
    TypeError, while exercising the REAL resume call path either way.
    """
    import inspect

    sig = inspect.signature(WebOverlay.start_chunk)
    if "resume_elapsed_s" in sig.parameters:
        return {
            "offset_s": KARAOKE_OFFSET_S,
            "resume_elapsed_s": elapsed_at_resume,
        }
    return {"offset_s": KARAOKE_OFFSET_S + elapsed_at_resume}


def _make_overlay(clock: FakeClock) -> WebOverlay:
    ov = WebOverlay({"show_overlay": True})
    # Inject the deterministic clock (real object, controllable time).
    ov._clock = clock
    return ov


def test_resume_preserves_elapsed_and_karaoke_position() -> None:
    clock = FakeClock()
    ov = _make_overlay(clock)

    # --- start the chunk (normal start: offset_s = karaoke_offset) ---
    ov.set_state("reading")
    ov.start_chunk(
        CHUNK_TEXT, CHUNK_DURATION, idx=0, total=1, offset_s=KARAOKE_OFFSET_S
    )

    # --- advance ~4s of playback ---
    clock.advance(4.0)
    mid = ov.snapshot()
    mid_elapsed = mid["elapsed"]
    mid_word = _karaoke_word_index(mid)
    assert mid_elapsed > 3.5, f"expected ~4s elapsed mid-chunk, got {mid_elapsed}"
    assert mid_word > 0, "karaoke should be past word 0 mid-chunk"

    # --- pause (engine.pause_toggle -> ov.set_paused(True)) ---
    ov.set_paused(True)
    paused_snap = ov.snapshot()
    assert paused_snap["is_paused"] is True
    # While paused the frozen elapsed must equal the paused-position.
    assert abs(paused_snap["elapsed"] - mid_elapsed) < 0.05

    # The user stares at the paused popup for a while.
    clock.advance(7.0)

    # --- resume: this is the EXACT double-reset race from the SPEC ---
    # 1) engine.pause_toggle calls set_paused(False) (rebases to preserve
    #    elapsed).
    elapsed_at_resume = paused_snap["elapsed"]
    ov.set_paused(False)
    # 2) the playback loop independently re-arms the karaoke clock for the
    #    audio tail. This mirrors playback._wait_for_chunk_end's resume
    #    branch exactly. On main these two calls double-reset _chunk_start
    #    and the snapshot elapsed collapses to ~0.
    remaining = CHUNK_DURATION - elapsed_at_resume
    ov.start_chunk(
        CHUNK_TEXT,
        remaining,
        idx=0,
        total=1,
        **_resume_start_chunk_kwargs(elapsed_at_resume),
    )

    # --- right after resume, no real time has passed ---
    resumed = ov.snapshot()
    resumed_elapsed = resumed["elapsed"]
    resumed_word = _karaoke_word_index(resumed)

    # The fix's contract: resume keeps the karaoke clock at the paused
    # position (NOT word 0, NOT elapsed ~0).
    assert resumed_elapsed > mid_elapsed - 0.5, (
        "RESUME RESET BUG: snapshot elapsed collapsed to "
        f"{resumed_elapsed:.3f}s after resume (paused at "
        f"{elapsed_at_resume:.3f}s) — karaoke restarts from word 0"
    )
    assert resumed_word >= mid_word, (
        f"karaoke jumped backward on resume: was word {mid_word}, "
        f"now word {resumed_word}"
    )

    # --- and the clock keeps moving forward from there ---
    clock.advance(1.0)
    later = ov.snapshot()
    assert later["elapsed"] > resumed_elapsed
