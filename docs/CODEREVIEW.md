# PipPal — Code Review (resolved 2026-05-03; refreshed for Core 0.2.3)

Multi-reviewer audit run before the original public release and
refreshed for the Core v0.2.3 documentation pass. Reviewers:

- **`ruff`** — full lint (`select = ["E","F","W","I","B","UP","RUF"]`)
- **`mypy`** — advisory static type-check, not a blocking release gate
  until the current Core typing debt is closed
- **`codex` CLI** — independent code-quality reviewer
- **Independent Claude Code agent** — second pair of eyes on each
  proposed fix

Status legend:

- ✅ **fixed** in commit history
- ⏳ **deferred** with rationale (architectural cleanups that don't
  fix an open bug)

End-to-end smoke test of the live app on Windows 11: **green**.
For current release-branch status, use the command output from
`python -m pytest -p no:cacheprovider` and `python -m ruff check .`.
Use `mypy` as an advisory type sweep, not as a go/no-go signal, until
it is made green on the supported Python path.

---

## HIGH — all closed

1. ✅ `voice_manager.py` lambda referenced `e` after the `except`
   block; Python 3 deletes the binding so any download error would
   `NameError` on the UI thread. Fixed: capture `str(e)` into a
   default arg.
2. ✅ Same NameError pattern in an extension package's install dialog.
3. ✅ Clipboard race in `_capture_selection` — added a per-engine
   lock; sentinel/save/restore can no longer interleave across two
   simultaneous hotkey actions.
4. ✅ Translate voice mutation — replaced in-place `self.config`
   mutation with a one-off backend instance threaded through
   `synthesize_and_play(..., backend=...)`. Shared config never
   touched.
5. ✅ `reset_backend` lock — both `reset_backend` and `_get_backend`
   now run under `self.lock`.
6. ✅ Token-read pattern — `_is_cancelled(my_token)` reads
   `self.token` under the lock; all hot-loop checks route through it.
7. ✅ Prefetch race — `_kick_prefetch` records the spawned thread
   and the main loop joins (`existing.join(timeout=20)`) before
   re-synthesising the same chunk. Refuses to race when the join
   times out — better a missing chunk than a corrupt WAV.
8. ✅ Seek-back regenerate — synth result is checked; on failure we
   `safe_unlink` and skip the chunk instead of spinning on a
   0-second deadline with a 0-byte WAV.
9. ✅ WAV leak on `winsound.PlaySound` failure — `safe_unlink` added
   before continuing.
10. ✅ Modifier-release list — `capture_for_action(action)` reads the
    configured hotkey combo from config and releases exactly its
    keys, plus the universal `ctrl/shift/alt/super` set.
11. ✅ Startup `piper.exe` check — `app.py` only requires Piper if
    `engine == "piper"`; alternative-engine setups boot fine.
12. ✅ `/read-file` IPC validation — extension allow-list (`.txt`,
    `.md`, `.log`, `.csv`, `.json`, `.html`, `.xml`), 200 KB cap,
    NUL-byte heuristic to reject binary content.
13. ✅ Pause-while-seek — the resume path checks `_skip_to` once
    more under lock before restarting playback.
14. ✅ `Overlay._on_click` exception safety — wrapped the handler
    dispatch in `_safe()`; an exception in `engine.stop()` no longer
    kills the Tk callback dispatcher.
15. ✅ `is_speaking` stuck `True` after Stop — `engine.stop()` now
    clears `is_speaking` directly so the tray icon flips to idle on
    cancel-exits where the playback loop returns without reaching
    its own clear. Regression test pins it.
16. ✅ Foreground-restore for tray-menu actions abandoned —
    investigation showed pystray's menu-close re-shifts focus AFTER
    the click handler returns, so any `SetForegroundWindow`
    succeeded then was promptly undone. Selection-driven actions
    moved out of the tray menu and live exclusively on the
    focus-preserving global hotkeys.

## MEDIUM — all closed

17. ✅ Synthesis-failure UX — first-chunk synth result is checked
    and surfaces "Synthesis failed" via the overlay instead of
    completing silently.
18. ✅ Backend-config mutation — `TTSBackend.__init__` now
    snapshot-copies its config dict, so a `apply_mood`-style
    mutation can't change a cached backend's voice mid-paragraph.
19. ✅ Per-text backend pinning — `play_one` captures
    `engine._get_backend()` once at the top and threads it through
    every prefetch / synth call. `reset_backend` mid-text affects
    only the next read.
20. ✅ Cancel-exit drains prefetch threads — `_cancel_exit(session)`
    waits up to 2 s for each in-flight prefetch before unlinking
    chunk files, so a still-running synth can't write a WAV after
    we cleaned up.
21. ✅ Hotkey rebind failures surfaced — `bind_hotkeys()` returns a
    list of `(action_id, combo, error)`; the Settings save path
    shows a `messagebox.showwarning` instead of saving a broken
    combo silently to disk.
22. ✅ Atomic save — `save_config` writes only the keys whose value
    differs from the current layered defaults, then `os.replace`.
    Plugin uninstall no longer strands stale defaults on disk;
    unknown keys are preserved verbatim.
23. ✅ `bind_all("<MouseWheel>")` leak — Settings and Voice Manager
    use `canvas.bind` (local) instead of `bind_all` (global), so
    closing the window stops hijacking scroll events.
24. ✅ Settings sync HTTP call — extension settings cards run remote
    fetches in a background thread and marshal results back via
    `self.win.after`.
25. ✅ Settings `_save` atomic — builds a `candidate` dict, calls
    `on_save` first, then `self.config.clear() / .update(candidate)`
    only on success.
26. ✅ Atomic file writes — both `save_config` and `save_history`
    write to a `.part` file then `os.replace`.
27. ✅ Command-server bind failure visible — `app.py` prints a clear
    "right-click integration disabled" message to stderr when the
    port can't be bound.
28. ✅ `context_menu_status() → "all" | "partial" | "none"` —
    Settings shows ⚠ for partial state and prompts re-install.
29. ✅ `urlretrieve` no timeout — the Voice Manager uses
    `urlopen(url, timeout=…)` with chunked write to a `.part` file
    then `os.replace`.
30. ✅ Mid-download dialog dismiss — `_alive()` guard around every
    `self.win.after` schedule across the install dialogs.

## LOW / SSOT — all closed

31. ✅ Hotkey & default consolidation — `pippal.plugins` now owns the
    action_id / config_key / label / default combo registration.
    Static `HOTKEY_ACTIONS` / `HOTKEY_KEYS` / `HOTKEY_FOR_ACTION`
    aliases removed; consumers iterate the registry.
32. ✅ Layered config — `load_config` returns
    `core_defaults + plugin_defaults + user_overrides`; only user
    overrides persist.
33. ✅ Backend cache requested-name — `_get_backend` caches against
    the requested engine name, so an unavailable-engine fallback
    doesn't reinstantiate every chunk.
34. ✅ JSON corruption logging + `.bak` — `load_config` and
    `load_history` rename the bad file to `.bak` and print to stderr
    instead of silently discarding.
35. ✅ `seek(delta)` consolidates `prev_chunk / replay_chunk /
    next_chunk` into a single `seek(±1 / 0)`.
36. ✅ Public contract tests — `tests/test_plugin_host.py` pins the
    plugin API third-party plugins code against (engine /
    ai_action / hotkey / settings card / tray item registries).

## Architecture notes

✅ **Ecosystem-grade entry-point discovery** — optional extensions are
loaded through Python entry points in the `pippal.plugins` group. The
public package owns the registry contract, not any concrete extension
package name; a broken extension logs loudly and Core continues with
built-in features.

---

## Tooling

`pytest` and `ruff` are the blocking Core release gate:

Run them yourself:

```bash
python -m pytest -p no:cacheprovider
python -m ruff check .
```

`mypy` remains configured for advisory type review, but this branch is
not green enough to treat it as a release gate. Run it explicitly when
checking type drift under the `src/` layout:

```bash
python -m mypy --ignore-missing-imports --cache-dir "${TMPDIR:-/tmp}/pippal-mypy" src/pippal
```
