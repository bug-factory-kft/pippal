"""First-run nudges that don't depend on a working TTS engine.

When the user triggers a synth-driven action and no engine is
actually ready (no voice on disk for the selected backend), we can't
synthesise the standard reply — so we play a pre-recorded WAV that
walks them through Settings → Voice Manager. The recording was made
once with a clean voice and bundled with the install.

The karaoke overlay still gets to render the script alongside the
audio: ``start_chunk(text, duration)`` paces its cursor purely off
the duration we hand it, and the duration we hand it IS the WAV's
length, so the cursor lands on the last word as the audio finishes.
"""

from __future__ import annotations

import sys
import threading
import wave
import winsound
from typing import TYPE_CHECKING

from .paths import ASSET_NO_VOICE_WAV
from .voices import installed_voices

if TYPE_CHECKING:  # pragma: no cover
    from .ui import Overlay


# Verbatim text of the bundled WAV. Kept here (next to the path it
# describes) so when we re-record we can update both in one place.
NO_VOICE_SCRIPT: str = (
    "Hi, I'm PipPal — but I can't read anything yet because no voice "
    "is installed. Right-click my icon in the system tray, open "
    "Settings, then Voice Manager. Pick a voice in your language, hit "
    "Install, and I'll be ready in a moment. See you soon."
)


def is_default_engine_ready() -> bool:
    """True when the always-available Piper backend has at least one
    voice on disk. Plugin-registered engines make their own readiness
    call via ``backend.is_available()``; this helper only covers the
    public package's own engine."""
    return bool(installed_voices())


def _wav_duration_s(path) -> float:
    """Wall-clock length of a PCM WAV in seconds. Returns 0.0 if the
    header is unreadable — caller falls back to a coarse estimate."""
    try:
        with wave.open(str(path), "rb") as w:
            frames = w.getnframes()
            rate = w.getframerate()
        return frames / rate if rate else 0.0
    except Exception:
        return 0.0


def play_no_voice_clip(overlay: "Overlay | None" = None) -> float:
    """Play the bundled "I can't read anything yet, install a voice"
    clip asynchronously and start the karaoke overlay alongside.

    Returns the WAV's wall-clock duration so the caller can schedule
    its own end-of-clip cleanup (overlay hide, is_speaking flip, etc.).
    Returns 0.0 when the WAV is absent — e.g. a stripped-down dev
    install with no onboarding folder.
    """
    if not ASSET_NO_VOICE_WAV.exists():
        print(
            f"[onboarding] no-voice clip missing at {ASSET_NO_VOICE_WAV}",
            file=sys.stderr,
        )
        return 0.0

    # Drive the karaoke cursor off the WAV's actual duration so its
    # last-word landing matches the audio's last syllable. If reading
    # the WAV header fails for any reason, fall back to a 14s default
    # — close to the recorded clip and better than no overlay at all.
    duration_s = _wav_duration_s(ASSET_NO_VOICE_WAV) or 14.0

    if overlay is not None:
        try:
            # Only "thinking" and "reading" actually show the overlay
            # (set_state hides it for any other value); plain "speaking"
            # was wrong and silently hid the panel. ``reading`` puts it
            # in karaoke-cursor mode, which is what start_chunk feeds.
            overlay.set_state("reading")
            overlay.start_chunk(NO_VOICE_SCRIPT, duration_s, idx=0, total=1)
        except Exception as exc:  # noqa: BLE001 — overlay quirks must
            # never block the audio cue.
            print(f"[onboarding] overlay sync failed: {exc}", file=sys.stderr)

    # SND_FILENAME so PlaySound doesn't try to interpret the path as a
    # registry alias. SND_ASYNC so the action handler returns
    # immediately. SND_NODEFAULT so a missing WAV at this point would
    # fail silently rather than play the Windows default beep.
    flags = (
        winsound.SND_FILENAME
        | winsound.SND_ASYNC
        | winsound.SND_NODEFAULT
    )

    def _play() -> None:
        try:
            winsound.PlaySound(str(ASSET_NO_VOICE_WAV), flags)
        except Exception as exc:  # noqa: BLE001 — we never want to
            # crash an action handler over an onboarding nicety.
            print(f"[onboarding] PlaySound failed: {exc}", file=sys.stderr)

    threading.Thread(target=_play, daemon=True).start()
    return duration_s
