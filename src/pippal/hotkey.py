"""Global hotkey manager built on `keyboard.hook` with a strict
exact-match suppressor.

Why not `keyboard.add_hotkey(combo, fn, suppress=True)`: that built-in
suppression has a partial-prefix matching quirk — it can swallow
keystrokes that aren't an exact match for any registered combo just
because they share modifiers with one (Win+Shift+R registered →
Win+Shift+S also gets eaten).

Why not Win32 `RegisterHotKey`: that API is first-come-first-served
across the whole machine. If Microsoft Teams / PowerToys / OneDrive
already grabbed Win+Shift+R when their process started, our register
returns ERROR_HOTKEY_ALREADY_REGISTERED and we never see the combo.

The compromise here: install a single low-level keyboard hook
(`keyboard.hook(..., suppress=True)`) and decide per event whether to
fire one of our callbacks AND swallow the keystroke. Strict matching
means the swallow only fires when the **exact** held-modifier set +
trigger key is one of ours. Hook position means we see the event
before Windows routes WM_HOTKEY to whoever called RegisterHotKey, so
we can still claim a combo even if another app holds it.

State integrity:
- Modifier state is read from Win32 ``GetAsyncKeyState`` at match
  time, **not** from a hook-tracked cache. The LL hook can miss
  ``up`` events while Windows is on the secure desktop (UAC,
  Ctrl+Alt+Del, lock screen); a cached set would go stale and cause
  false matches when the user later types a plain letter that happens
  to complete the ghosted combo.
- Non-modifier keys are tracked between their first ``down`` and the
  matching ``up`` so that holding a registered combo (Windows fires
  ``down`` every ~30 ms while a key is held) does NOT re-spawn the
  handler thread on every repeat. The handler runs once on the first
  ``down``; subsequent repeats are still suppressed but not re-fired.
"""

from __future__ import annotations

import sys
import threading
from collections.abc import Callable, Iterable, Mapping

# Public combo-name aliases. Stored as frozensets so the matcher can
# compare in O(1) regardless of the order the user pressed modifiers
# in. The library reports "left ctrl" / "right ctrl" etc.; we
# normalise both sides to a single token so a combo string only ever
# names a logical modifier ("ctrl"), not a side.
_MOD_ALIASES: dict[str, str] = {
    "left ctrl":     "ctrl",
    "right ctrl":    "ctrl",
    "ctrl":          "ctrl",
    "control":       "ctrl",
    "left shift":    "shift",
    "right shift":   "shift",
    "shift":         "shift",
    "left alt":      "alt",
    "right alt":     "alt",
    "alt":           "alt",
    "left windows":  "win",
    "right windows": "win",
    "windows":       "win",
    "win":           "win",
    "super":         "win",
}


# ---------------------------------------------------------------------------
# Win32 modifier-state polling
# ---------------------------------------------------------------------------
# We deliberately bypass the keyboard library's `is_pressed` because that
# is derived from the same hook-event stream that can drop "up" events on
# a desktop switch. ``GetAsyncKeyState`` is updated by the kernel and
# stays in sync even across UAC / secure desktop transitions.

_VK_LSHIFT   = 0xA0
_VK_RSHIFT   = 0xA1
_VK_LCONTROL = 0xA2
_VK_RCONTROL = 0xA3
_VK_LMENU    = 0xA4
_VK_RMENU    = 0xA5
_VK_LWIN     = 0x5B
_VK_RWIN     = 0x5C


def _is_vk_pressed(vk: int) -> bool:
    """Return True if the given virtual-key is physically held according
    to the kernel. The high bit of GetAsyncKeyState's return is the
    "currently down" flag; the low bit is the unrelated "pressed since
    last call" toggle which we do not consume."""
    if not hasattr(__import__("ctypes"), "windll"):
        return False
    import ctypes
    return bool(ctypes.windll.user32.GetAsyncKeyState(vk) & 0x8000)


def _physical_modifiers() -> frozenset[str]:
    """Snapshot of which logical modifiers are currently held.

    Aggregates the left/right virtual-keys for each modifier so a combo
    that names only ``shift`` matches whether the user holds the left
    Shift, the right Shift, or both. Reads come straight from
    ``GetAsyncKeyState`` to be authoritative, even after the LL hook
    missed an ``up`` event during a secure-desktop switch."""
    mods: set[str] = set()
    if _is_vk_pressed(_VK_LCONTROL) or _is_vk_pressed(_VK_RCONTROL):
        mods.add("ctrl")
    if _is_vk_pressed(_VK_LSHIFT) or _is_vk_pressed(_VK_RSHIFT):
        mods.add("shift")
    if _is_vk_pressed(_VK_LMENU) or _is_vk_pressed(_VK_RMENU):
        mods.add("alt")
    if _is_vk_pressed(_VK_LWIN) or _is_vk_pressed(_VK_RWIN):
        mods.add("win")
    return frozenset(mods)


def _normalise_key(name: str) -> str:
    if not name:
        return ""
    return _MOD_ALIASES.get(name.lower(), name.lower())


def _is_modifier(key: str) -> bool:
    return key in {"ctrl", "shift", "alt", "win"}


def parse_combo(combo: str) -> tuple[frozenset[str], str] | None:
    """Translate ``windows+shift+r`` into ``(frozenset({'win','shift'}), 'r')``.

    Rejects malformed combos: must contain **exactly one** non-modifier
    trigger key. ``"ctrl+shift"`` (no trigger) and ``"ctrl+r+x"`` (two
    triggers) both return ``None`` so the Settings UI can surface a
    parse failure instead of silently registering something that will
    never fire."""
    parts = [p.strip().lower() for p in (combo or "").split("+") if p.strip()]
    mods: set[str] = set()
    triggers: list[str] = []
    for p in parts:
        normalised = _MOD_ALIASES.get(p, p)
        if _is_modifier(normalised):
            mods.add(normalised)
        else:
            triggers.append(normalised)
    if len(triggers) != 1:
        return None
    return frozenset(mods), triggers[0]


def duplicate_combo_failures(
    config: Mapping[str, object],
    actions: Iterable[tuple[str, str, str, str]],
) -> list[tuple[str, str, str]]:
    """Return `(action_id, combo, reason)` for duplicate valid combos.

    Invalid combos are left to ``register`` so the existing parse-error
    path can report them. This helper only catches the silent-overwrite
    case where two action rows parse to the same hotkey identity.
    """
    seen: dict[tuple[frozenset[str], str], tuple[str, str]] = {}
    failures: list[tuple[str, str, str]] = []
    for action_id, key, _label, default_combo in actions:
        combo = str(config.get(key, default_combo) or "").strip()
        if not combo:
            continue
        parsed = parse_combo(combo)
        if parsed is None:
            continue
        prior = seen.get(parsed)
        if prior is not None:
            prior_action, _prior_combo = prior
            failures.append((
                action_id,
                combo,
                f"duplicate combo also used by {prior_action}",
            ))
            continue
        seen[parsed] = (action_id, combo)
    return failures


class HotkeyManager:
    """Single low-level hook + a strict exact-match dispatcher."""

    def __init__(self) -> None:
        # ``_handlers`` is replaced atomically (copy-on-write) by
        # ``register`` / ``unregister_all`` so the read path on the hook
        # thread doesn't need to hold the lock for the lookup itself —
        # only for fetching the dict reference.
        self._handlers: dict[tuple[frozenset[str], str], Callable[[], None]] = {}
        # Non-modifier keys we have seen "down" but not yet "up" for. Used
        # to deduplicate Windows key-repeat events so a held combo only
        # fires the handler once per physical press.
        self._held_non_mod: set[str] = set()
        # Of the keys in ``_held_non_mod``, the subset whose first ``down``
        # matched a registered combo. We keep suppressing repeats for
        # those (so the OS doesn't get half a held key) and pass through
        # repeats for non-matched keys.
        self._suppressed_non_mod: set[str] = set()
        self._lock = threading.Lock()
        self._hook_handle: object | None = None
        self._started: bool = False
        self._failures: list[tuple[str, str]] = []
        self._is_windows = sys.platform == "win32"
        # Imported lazily so `import pippal.hotkey` doesn't pull
        # `keyboard` (a Windows-only API on the user's PATH) on
        # non-Windows platforms.
        self._keyboard = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def start(self) -> None:
        if not self._is_windows or self._hook_handle is not None:
            return
        try:
            import keyboard
        except Exception as exc:
            print(f"[hotkey] could not import 'keyboard' lib: {exc}",
                  file=sys.stderr)
            with self._lock:
                self._failures.append(("(start)", f"keyboard import failed: {exc}"))
            return
        self._keyboard = keyboard
        try:
            # `suppress=True` lets the callback's return value decide
            # whether each event reaches the foreground app.
            self._hook_handle = keyboard.hook(self._on_event, suppress=True)
            self._started = True
        except Exception as exc:
            print(f"[hotkey] could not install keyboard hook: {exc}",
                  file=sys.stderr)
            with self._lock:
                self._failures.append(("(start)", f"hook install failed: {exc}"))

    def stop(self) -> None:
        if self._hook_handle is None or self._keyboard is None:
            return
        try:
            self._keyboard.unhook(self._hook_handle)
        except Exception:
            pass
        self._hook_handle = None
        self._started = False
        with self._lock:
            self._handlers = {}
            self._held_non_mod.clear()
            self._suppressed_non_mod.clear()

    def register(self, combo: str, callback: Callable[[], None]) -> bool:
        """Add a combo. Returns False if the combo string is unparseable
        or the hook never started; otherwise the matcher picks it up
        immediately. Duplicate combos are rejected so one action cannot
        silently replace another."""
        parsed = parse_combo(combo)
        if parsed is None:
            with self._lock:
                self._failures.append((combo, "unparseable combo"))
            return False
        if not self._started:
            with self._lock:
                self._failures.append((combo, "hook not running"))
            return False
        # Copy-on-write swap so the hook callback (which reads
        # ``self._handlers`` without locking the lookup itself) always
        # sees a consistent, fully-populated dict.
        with self._lock:
            if parsed in self._handlers:
                self._failures.append((combo, "duplicate combo"))
                return False
            new_handlers = dict(self._handlers)
            new_handlers[parsed] = callback
            self._handlers = new_handlers
        return True

    def unregister_all(self) -> None:
        """Drop every registered combo. Used on Settings save before
        rebinding so removed combos stop suppressing immediately. Does
        NOT touch the held-key tracking — those reflect physical state
        and would only get out of sync if we tampered with them."""
        with self._lock:
            self._handlers = {}

    def failures(self) -> list[tuple[str, str]]:
        with self._lock:
            f = list(self._failures)
            self._failures.clear()
        return f

    # ------------------------------------------------------------------
    # Hook callback (runs on the keyboard lib's hook thread)
    # ------------------------------------------------------------------

    def _on_event(self, event: object) -> bool | None:
        """Returning False suppresses the event; returning True / None
        lets it pass through. We swallow ONLY when the exact
        (modifiers held + trigger key) tuple matches a registered
        combo — anything else flows through to the foreground app.

        Modifier events are not tracked in our own cache anymore; the
        match path queries Win32 ``GetAsyncKeyState`` directly so a
        missed ``up`` (UAC / secure desktop) cannot leave us with a
        ghost modifier."""
        try:
            name = _normalise_key(getattr(event, "name", "") or "")
            event_type = getattr(event, "event_type", "")

            if not name:
                return True

            # Modifier transitions: we don't track them. The non-modifier
            # path queries the OS directly when it needs the answer.
            if _is_modifier(name):
                return True

            if event_type == "down":
                # Snapshot the handler dict ONCE — copy-on-write means
                # this reference is internally consistent even if
                # ``register`` swaps a new dict in mid-evaluation.
                handlers = self._handlers

                with self._lock:
                    is_repeat = name in self._held_non_mod
                    self._held_non_mod.add(name)
                    if is_repeat:
                        # Already decided suppression on the first down.
                        # Reuse that decision so the OS sees a consistent
                        # gesture (all-suppressed or all-passed) across
                        # the entire held-key sequence.
                        suppressed = name in self._suppressed_non_mod

                if is_repeat:
                    return False if suppressed else True

                # First ``down`` for this physical press — query the OS
                # for current modifier state and decide.
                mods_now = _physical_modifiers()
                handler = handlers.get((mods_now, name))
                if handler is None:
                    return True  # not our combo, pass through

                # Matched — remember the suppress decision so repeats
                # stay suppressed too, then dispatch off the hook
                # thread (the OS input pipeline can't tolerate slow
                # callbacks).
                with self._lock:
                    self._suppressed_non_mod.add(name)
                threading.Thread(
                    target=self._safe_call, args=(handler,), daemon=True,
                ).start()
                return False  # SUPPRESS — only this exact combo

            if event_type == "up":
                with self._lock:
                    self._held_non_mod.discard(name)
                    self._suppressed_non_mod.discard(name)
                return True

            return True
        except Exception as exc:
            # A crashing hook callback wedges Windows input — swallow
            # any unexpected exception and let the event through.
            print(f"[hotkey] hook callback error: {exc}", file=sys.stderr)
            return True

    def _safe_call(self, fn: Callable[[], None]) -> None:
        try:
            fn()
        except Exception as exc:
            print(f"[hotkey] handler crashed: {exc}", file=sys.stderr)
