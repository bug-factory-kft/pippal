"""_EngineActionsMixin — action-impl methods for TTSEngine.

Extracted verbatim from ``engine.py`` (lines 343-601) to keep every
module under the 600-line guard.  All instance state lives in
``TTSEngine.__init__`` (not moved); this mixin reads/writes ``self.*``
exactly as before.  No ``__init__``, no ``super()`` call.

CORE-NO-PRO-LEAK: this module contains zero references to
``pippal_pro`` or any Pro-only feature.
"""

from __future__ import annotations

import threading
import winsound
from pathlib import Path

from . import clipboard_capture, playback
from .engines import TTSBackend, make_backend


class _EngineActionsMixin:
    """Pure-method mixin — no ``__init__``, no ``super()``."""

    def _maybe_play_onboarding(self) -> bool:
        """When no engine is ready to synth (no voice installed yet),
        play the bundled onboarding clip — with the same karaoke
        overlay we'd show during a normal Read — and tell the caller
        to bail. Returns True when onboarding fired so the caller can
        return early instead of starting a synth that would silently
        fail."""
        backend = self._get_backend()
        if backend.is_ready():
            return False
        self._start_onboarding()
        return True

    def _start_onboarding(self) -> None:
        """Kick off (or restart) the no-voice onboarding clip + karaoke
        overlay. Reuses the engine's normal speak-state so the existing
        Stop / Replay buttons in the mini-player Just Work — the timer
        finishes the visuals when the audio runs out, but Stop can
        cancel both, and Replay calls back into here for a re-play."""
        from . import onboarding

        # Cancel any in-flight onboarding before starting a fresh one;
        # otherwise the previous timer would race with the new one and
        # could flip the overlay to "done" half-way through replay.
        if self._onboarding_timer is not None:
            self._onboarding_timer.cancel()
            self._onboarding_timer = None
        try:
            winsound.PlaySound(None, winsound.SND_PURGE)
        except Exception:
            pass

        ov = self._overlay()
        with self.lock:
            self.token += 1
            my_token = self.token
            # Pretend we're synthesising — Stop handler in the overlay
            # looks at is_speaking to decide whether to flip the panel
            # to "done", and we want it to.
            self.is_speaking = True
            self._onboarding_active = True

        duration = onboarding.play_no_voice_clip(overlay=ov)
        if duration <= 0:
            # WAV missing — undo the speak-state we just set so the
            # tray icon doesn't sit there pretending to read.
            with self.lock:
                self.is_speaking = False
                self._onboarding_active = False
            return

        def _finish() -> None:
            with self.lock:
                # Stop / next replay bumped the token — leave the
                # state alone, the new flow owns it.
                if self.token != my_token or not self._onboarding_active:
                    return
                self._onboarding_active = False
                self.is_speaking = False
            if ov is not None:
                try:
                    ov.set_state("done")
                except Exception:
                    pass

        self._onboarding_timer = threading.Timer(duration, _finish)
        self._onboarding_timer.daemon = True
        self._onboarding_timer.start()

    def _get_backend(self) -> TTSBackend:
        # Cache key is the *requested* engine name, NOT the concrete
        # class — when an extension-supplied engine is requested but
        # unavailable, we want the Piper fallback to stay cached
        # (otherwise we'd rebuild on every chunk). Settings save and
        # mood change explicitly call ``reset_backend()`` /
        # ``reload_engine()`` to invalidate; the engine never tries to
        # hot-detect re-registrations on its own. (Codex' guidance:
        # require an explicit reload API instead of magic invalidation.)
        wanted = (self.config.get("engine") or "piper").lower()
        with self.lock:
            if self._backend is None or self._backend_name != wanted:
                self._backend = make_backend(self.config)
                self._backend_name = wanted
                self._backend_cls = type(self._backend)
            return self._backend

    def _synthesize(
        self,
        text: str,
        out_path: Path,
        backend: TTSBackend | None = None,
    ) -> bool:
        b = backend if backend is not None else self._get_backend()
        return b.synthesize(text, out_path)

    # Backwards-compat alias for places that imported from tests.
    def _capture_selection(self, hotkey_combo: str = "") -> str:
        return clipboard_capture.capture_selection(self, hotkey_combo)

    def _capture_for_action(self, action: str) -> str:
        return clipboard_capture.capture_for_action(self, action)

    def _synthesize_and_play(
        self,
        text: str,
        my_token: int,
        backend: TTSBackend | None = None,
    ) -> None:
        playback.synthesize_and_play(self, text, my_token, backend=backend)

    # ------------------------------------------------------------------
    # Top-level flows that don't fit a worker module
    # ------------------------------------------------------------------

    def _speak_selection_impl(self) -> None:
        if self._maybe_play_onboarding():
            return
        with self.lock:
            self.token += 1
            my_token = self.token
            self._queue = []
        try:
            winsound.PlaySound(None, winsound.SND_PURGE)
        except Exception:
            pass

        ov = self._overlay()
        if ov is not None:
            ov.set_state("thinking")

        text = clipboard_capture.capture_for_action(self, "speak")
        if self._is_cancelled(my_token):
            return
        if not text:
            self._record_activation_capture_failure()
            if ov is not None:
                ov.show_message("No text selected")
            return

        self._mark_activation_selected_text_complete()
        self._remember(text)
        with self.lock:
            self.is_speaking = True
        # ISSUE 2 — selection CAPTURED (#265 window closed): post-capture
        # ``loading`` shows the overlay instantly while synth runs.
        if ov is not None:
            ov.set_state("loading")
        playback.synthesize_and_play(self, text, my_token)

    def _queue_selection_impl(self) -> None:
        if self._maybe_play_onboarding():
            return
        text = clipboard_capture.capture_for_action(self, "queue")
        if not text:
            ov = self._overlay()
            if ov is not None:
                ov.show_message("No text selected")
            return
        with self.lock:
            speaking = self.is_speaking
            if speaking:
                self._queue.append(text)
                qlen = len(self._queue)
        if speaking:
            ov = self._overlay()
            if ov is not None:
                ov.show_message(f"Queued — {qlen} pending")
            return
        # Idle → behave like Read. Selection already CAPTURED above, so
        # use the visible post-capture ``loading`` state (ISSUE 2).
        self._remember(text)
        with self.lock:
            self.token += 1
            my_token = self.token
            self.is_speaking = True
        ov = self._overlay()
        if ov is not None:
            ov.set_state("loading")
        playback.synthesize_and_play(self, text, my_token)

    def _read_text_impl(self, text: str) -> None:
        if self._maybe_play_onboarding():
            return
        text = (text or "").strip()
        if not text:
            return
        with self.lock:
            self.token += 1
            my_token = self.token
            self.is_speaking = True
            self._queue = []
        try:
            winsound.PlaySound(None, winsound.SND_PURGE)
        except Exception:
            pass
        ov = self._overlay()
        if ov is not None:
            # ISSUE 2 — text in hand (no capture, no #265 risk): instant
            # overlay via post-capture ``loading``.
            ov.set_state("loading")
        self._remember(text)
        playback.synthesize_and_play(self, text, my_token)

    def _replay_text_impl(self, text: str) -> None:
        if self._maybe_play_onboarding():
            return
        text = (text or "").strip()
        if not text:
            return
        with self.lock:
            self.token += 1
            my_token = self.token
            self.is_speaking = True
            self._queue = []
        try:
            winsound.PlaySound(None, winsound.SND_PURGE)
        except Exception:
            pass
        ov = self._overlay()
        if ov is not None:
            # ISSUE 2 — replay text in hand: instant ``loading``.
            ov.set_state("loading")
        playback.synthesize_and_play(self, text, my_token)
