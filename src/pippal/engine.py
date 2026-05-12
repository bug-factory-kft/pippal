"""TTSEngine — the orchestration layer.

Owns the high-level state (token, lock, queue, history, mini-player
status) and delegates the heavy work to focused modules:

- :mod:`pippal.clipboard_capture`  selection capture
- :mod:`pippal.playback`           synthesis + audio loop

Extension packages can plug in additional behaviours through the
plugin host (e.g. AI actions, audio export) — those handlers run
out-of-process from this module's perspective.

UI updates flow through an `overlay_ref` callable so the engine never
imports Tk."""

from __future__ import annotations

import threading
import winsound
from collections.abc import Callable
from pathlib import Path
from typing import Any, Protocol

from . import clipboard_capture, playback, plugins
from .engines import TTSBackend, make_backend
from .history import add_history


class _OverlayProto(Protocol):
    def set_state(self, state: str) -> None: ...
    def show_message(self, msg: str) -> None: ...
    def set_action_label(self, label: str | None) -> None: ...
    def set_paused(self, paused: bool) -> None: ...
    def start_chunk(self, text: str, duration: float, idx: int, total: int,
                    offset_s: float = ...) -> None: ...


class _RootProto(Protocol):
    def after(self, ms: int, fn: Callable[..., Any]) -> Any: ...


class TTSEngine:
    """Top-level controller.

    Holds the playback state machine and exposes coarse-grained methods
    for the tray menu and global hotkeys."""

    def __init__(
        self,
        root: _RootProto,
        config: dict[str, Any],
        overlay_ref: Callable[[], _OverlayProto | None],
    ) -> None:
        self.root = root
        self.config = config
        self.overlay_ref = overlay_ref

        # Owns: token, is_speaking, _is_paused, _queue, _history,
        #       _chunks/_chunk_paths/_chunk_idx/_skip_to, _backend cache.
        self.lock = threading.Lock()
        # Serialises clipboard capture across hotkeys / tray actions so
        # two near-simultaneous reads can't interleave their probes.
        self._capture_lock = threading.Lock()

        self.token: int = 0
        self.is_speaking: bool = False

        # Onboarding-clip bookkeeping. We re-use the regular tray-app
        # state machinery (is_speaking + overlay state) so the existing
        # stop/replay buttons just work, but also need to cancel the
        # auto-hide timer when the user stops mid-clip.
        self._onboarding_active: bool = False
        self._onboarding_timer: threading.Timer | None = None

        self._backend: TTSBackend | None = None
        self._backend_name: str | None = None  # name we cached FOR
        self._backend_cls: type | None = None  # concrete class we cached

        # Mini-player state. The engine OWNS these fields (every read /
        # write goes through self.lock) but `pippal.playback` is the
        # only writer that mutates them — `_prepare_first_chunk` /
        # `_play_chunk` populate them, `seek()` and `pause_toggle()`
        # only ever read or set the navigation flags.
        self._chunks: list[str] = []
        self._chunk_paths: list[Path] = []
        self._chunk_idx: int = 0
        self._skip_to: int | None = None
        self._is_paused: bool = False

        self._queue: list[str] = []

        # Recent history (in-memory; persisted via attach_history).
        self._history: list[str] = []
        self._history_save: Callable[[list[str]], None] | None = None

    # ------------------------------------------------------------------
    # Public API: tray menu / hotkey entrypoints (always async)
    # ------------------------------------------------------------------

    def _async(self, fn: Callable[..., Any], *args: Any) -> None:
        threading.Thread(target=fn, args=args, daemon=True).start()

    def speak_selection_async(self) -> None:
        self._async(self._speak_selection_impl)

    def queue_selection_async(self) -> None:
        self._async(self._queue_selection_impl)

    def dispatch_plugin_action(self, action_id: str) -> None:
        """Run a registered plugin action.

        Resolution goes through the plugin host (`pippal.plugins`) so
        the engine has zero name-awareness of which handler is active.
        In a core build no plugin action is registered and this method
        is a silent no-op."""
        handler = plugins.get_plugin_action(action_id)
        if handler is None:
            return
        # Same gate as Speak / Queue: when no voice is installed, play
        # the onboarding clip rather than letting the plugin handler
        # do its work and then fail at the synth boundary. Cheaper to
        # short-circuit before the handler runs at all — handlers may
        # do meaningful network / disk work before reaching synth.
        self._async(self._dispatch_plugin_action_impl, action_id, handler)

    def _dispatch_plugin_action_impl(
        self, action_id: str, handler: Callable[..., Any],
    ) -> None:
        if self._maybe_play_onboarding():
            return
        handler(self, action_id)


    def replay_text(self, text: str) -> None:
        self._async(self._replay_text_impl, text)

    def read_text_async(self, text: str) -> None:
        """Read caller-provided text as a new user action.

        Unlike `replay_text`, this records the text in Recent history.
        Used by the command server and file-open helper where the text
        did not come from an existing history entry.
        """
        self._async(self._read_text_impl, text)

    def stop(self) -> None:
        with self.lock:
            self.token += 1
            was_speaking = self.is_speaking
            # Stop is the authoritative reset: clear is_speaking now so
            # the tray icon flips to idle even on cancel-exits where the
            # playback loop returns without reaching its own clear.
            self.is_speaking = False
            self._is_paused = False
            self._queue = []
            self._onboarding_active = False
        if self._onboarding_timer is not None:
            self._onboarding_timer.cancel()
            self._onboarding_timer = None
        try:
            winsound.PlaySound(None, winsound.SND_PURGE)
        except Exception:
            pass
        ov = self._overlay()
        if ov is not None:
            ov.set_paused(False)
            if was_speaking:
                ov.set_state("done")

    def pause_toggle(self) -> None:
        with self.lock:
            if not self.is_speaking and not self._is_paused:
                return
            self._is_paused = not self._is_paused
            paused = self._is_paused
        ov = self._overlay()
        if paused:
            try:
                winsound.PlaySound(None, winsound.SND_PURGE)
            except Exception:
                pass
            if ov is not None:
                ov.set_paused(True)
        else:
            if ov is not None:
                ov.set_paused(False)

    @property
    def is_paused(self) -> bool:
        with self.lock:
            return self._is_paused

    # ----- mini-player navigation -----
    def seek(self, delta: int) -> None:
        """Move forward/backward `delta` chunks (or 0 to replay current)."""
        with self.lock:
            if not self._chunks:
                return
            target = max(0, min(len(self._chunks) - 1, self._chunk_idx + delta))
            self._skip_to = target
        try:
            winsound.PlaySound(None, winsound.SND_PURGE)
        except Exception:
            pass

    def prev_chunk(self) -> None:
        if self._onboarding_active:
            self._start_onboarding()
            return
        self.seek(-1)

    def next_chunk(self) -> None:
        if self._onboarding_active:
            # No "next" inside a single onboarding clip; just replay.
            self._start_onboarding()
            return
        self.seek(+1)

    def replay_chunk(self) -> None:
        if self._onboarding_active:
            self._start_onboarding()
            return
        self.seek(0)

    # ----- history -----
    def attach_history(
        self,
        items: list[str],
        save_callback: Callable[[list[str]], None] | None,
    ) -> None:
        with self.lock:
            self._history = list(items or [])
            self._history_save = save_callback

    def get_history(self) -> list[str]:
        with self.lock:
            return list(self._history)

    def clear_history(self) -> None:
        with self.lock:
            self._history = []
            save = self._history_save
        if save is not None:
            try:
                save([])
            except Exception:
                pass

    def queue_length(self) -> int:
        with self.lock:
            return len(self._queue)

    def reset_backend(self) -> None:
        """Drop the cached backend so the next synth picks up new
        config. Same effect as `reload_engine()` — kept as the legacy
        name because Settings + mood-change still call it."""
        with self.lock:
            self._backend = None
            self._backend_name = None
            self._backend_cls = None

    def reload_engine(self) -> None:
        """Public API: force the engine to rebuild on the next synth.
        Use this after changing voice / engine config or after a
        plugin install if the engine should pick up new defaults."""
        self.reset_backend()

    # ------------------------------------------------------------------
    # Helpers used by the worker modules
    # ------------------------------------------------------------------

    def _overlay(self) -> _OverlayProto | None:
        return self.overlay_ref() if self.overlay_ref else None

    def _is_cancelled(self, my_token: int) -> bool:
        with self.lock:
            return my_token != self.token

    def _remember(self, text: str) -> None:
        text = (text or "").strip()
        if not text:
            return
        with self.lock:
            self._history = add_history(self._history, text)
            snapshot = list(self._history)
            save = self._history_save
        if save is not None:
            try:
                save(snapshot)
            except Exception:
                pass

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
            if ov is not None:
                ov.show_message("No text selected")
            return

        self._remember(text)
        with self.lock:
            self.is_speaking = True
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
        # Idle → behave like Read.
        self._remember(text)
        with self.lock:
            self.token += 1
            my_token = self.token
            self.is_speaking = True
        ov = self._overlay()
        if ov is not None:
            ov.set_state("thinking")
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
            ov.set_state("thinking")
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
            ov.set_state("thinking")
        playback.synthesize_and_play(self, text, my_token)
