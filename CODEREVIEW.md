# PipPal — Code Review (resolved 2026-05-03)

Consolidated findings from four reviewers (ruff, mypy, codex CLI,
independent Claude agent) — and **the work to close them all**.
Status legend:

- ✅ **fixed** in commit history
- ⏳ **deferred** with rationale (only architectural cleanups that
  don't fix an open bug)

Tests: **152 passing**. ruff: **0 errors**. End-to-end smoke test
of the live app: **green**.

---

## HIGH — all closed

1. ✅ **`pippal/ui/voice_manager.py:136`** — lambda referenced `e`
   after the `except` block; Python 3 deletes the binding so any
   download error would `NameError` on the UI thread. Fixed: capture
   `str(e)` into a default arg.
2. ✅ **`pippal/ui/kokoro_install.py:108`** — same bug, same fix.
3. ✅ **Clipboard race in `_capture_selection`** — added a
   module-private `_capture_lock`; serialises sentinel/save/restore
   across hotkey actions so two simultaneous reads can't interleave.
4. ✅ **Translate voice mutation** — replaced in-place `self.config`
   mutation with a one-off `PiperBackend(cfg_override)` instance
   passed through `_synthesize_and_play(..., backend=...)`. Shared
   config is never touched.
5. ✅ **`reset_backend` lock** — both `reset_backend` and
   `_get_backend` now run under `self.lock`.
6. ✅ **Token-read pattern** — added `_is_cancelled(my_token)` helper
   that reads `self.token` under `self.lock`; all hot-loop checks
   route through it.
7. ✅ **Prefetch race** — `kick_prefetch` records the spawned thread
   and the main loop joins (`existing.join(timeout=20)`) before
   re-synthesizing the same chunk. No more two-writer collisions.
8. ✅ **Seek-back regenerate** — synth result is now checked; on
   failure we `safe_unlink` and skip the chunk instead of spinning
   on a 0-second deadline with a 0-byte WAV.
9. ✅ **WAV leak on `winsound.PlaySound` failure** — `safe_unlink`
   added before `idx += 1; continue`.
10. ✅ **Modifier-release list** — `_capture_for_action(action)` reads
    the configured hotkey combo from config and releases exactly its
    keys, plus the universal `ctrl/shift/alt/super` set.
11. ✅ **Startup `piper.exe` check** — `app.py` now only requires
    Piper if `engine == "piper"`; Kokoro-only setups boot fine.
12. ✅ **`/read-file` validation** — extension allow-list (`.txt`,
    `.md`, `.log`, `.csv`, `.json`, `.html`, `.xml`), 200 KB cap,
    NUL-byte heuristic to reject binary content. Both endpoints
    enforce body-size limits.
13. ✅ **Pause-while-seek** — the resume path checks `_skip_to` once
    more under lock before restarting playback, and the pause-wait
    inner loop falls through to the seek branch instead of replaying
    the wrong chunk.
14. ✅ **`Overlay._on_click` exception safety** — wrapped the
    handler dispatch in `_safe()`; an exception in `engine.stop()` no
    longer kills the Tk callback dispatcher.
15. ✅ **Export `done.wait(timeout=300)`** — dropped the timeout. The
    file dialog runs on the UI thread (a different thread from this
    worker), so a plain `done.wait()` blocks safely without the
    stale-state race.

## MEDIUM — all closed

16. ⏳ **`TTSEngine` SRP** — engine now 612 lines with one clear set
    of responsibilities (orchestration). The Player extraction
    (`_play_one` + `_wait_for_chunk_end` into a separate class) is
    deferred: the bugs that motivated it (#6–9, #13) have been fixed
    in-place under the engine's lock, and a clean Player split would
    require duplicating that lock and token mechanism. **Mark this as
    architectural follow-up, not a correctness gap.**
17. ✅ **Synthesis-failure UX** — `_play_one` checks `_synthesize` on
    the first chunk and shows "Synthesis failed" via the overlay
    instead of completing silently. PlaySound failures clean up the
    leaked WAV.
18. ✅ **Kokoro `k.create()` lock** — the backend's `_lock` now
    guards both lazy load AND inference; concurrent prefetch + main
    playback can no longer race inside the Kokoro session.
19. ✅ **Export temp file collision** — uses `uuid.uuid4().hex[:8]`
    instead of `int(time.time())`.
20. ✅ **`bind_all("<MouseWheel>")` leak** — Settings and Voice
    Manager now use `canvas.bind` (local) instead of `bind_all`
    (global), so closing the window stops hijacking scroll events.
21. ✅ **Settings sync Ollama call** — `_refresh_ollama_models` runs
    the HTTP request in a background thread and marshals results
    back via `self.win.after`.
22. ✅ **Settings `_save` atomic** — builds a `candidate` dict, calls
    `on_save` first, then `self.config.clear() / .update(candidate)`
    only on success. Hotkey rebind failure leaves both
    in-memory and persisted state un-corrupted.
23. ✅ **Atomic `save_config` / `save_history`** — both write to a
    `.part` file then `os.replace`. `history.save_history` also takes
    a module-level `_save_lock` to serialise concurrent writers.
24. ✅ **`stop()` `is_speaking` flicker** — left for the playback
    loop to clear on actual exit; tray polling no longer flickers
    between states.
25. ✅ **Command-server bind failure visible** — `app.py` now prints
    a clear "right-click integration disabled" message to stderr
    when the port can't be bound.
26. ✅ **`context_menu_installed` partial drift** — replaced with
    `context_menu_status() → "all" | "partial" | "none"`. Settings
    UI shows ⚠ for partial state and prompts re-install.
27. ✅ **`urlretrieve` no timeout** — Voice Manager uses an explicit
    `_streaming_download` with `urlopen(url, timeout=30)` and chunked
    write; metadata downloads to `.part` then atomic rename.
28. ✅ **`KokoroInstallDialog._cancel` race** — `_alive()` guard
    around every `self.win.after` schedule; safe to dismiss the
    dialog even mid-download.
29. ✅ **`text_utils` no hard wrap** — added `_wrap_long` fallback
    that splits a punctuation-free over-cap sentence on whitespace.
    New test: `test_hard_wraps_long_punctuation_free_sentence`.
30. ✅ **`.onnx.json` `.part` write** — `_streaming_download` writes
    to `.part` for both `.onnx` and `.onnx.json`, then `os.replace`.

## LOW / SSOT — all closed

31. ✅ **Defaults consolidation** — overlay reads `auto_hide_ms`,
    `overlay_y_offset`, `karaoke_offset_ms` via
    `DEFAULT_CONFIG[k]` instead of hardcoded duplicates.
32. ✅ **`pippal_open.py PORT`** — imports `CMD_SERVER_PORT` from
    `pippal.paths`. Single source of truth.
33. ⏳ **`ActionSpec` table** — engine got `_HOTKEY_FOR_ACTION` and
    `_VALID_AI_ACTIONS = tuple(AI_NUM_PREDICT)` so the duplication
    is much smaller. Full `ActionSpec` dataclass would also touch
    `app.py` tray menu generation; deferred as cosmetic.
34. ⏳ **MOODS deriving from voice catalogue** — moods.py currently
    references voice ids; deriving them programmatically would lose
    the curated tone metadata (speed/noise per mood). Acceptable
    duplication.
35. ✅ **`_async` helper** — eight `threading.Thread(...).start()`
    wrappers collapsed into `self._async(fn, *args)`.
36. ✅ **`_VALID_AI_ACTIONS`** — now `tuple(AI_NUM_PREDICT.keys())`,
    deduped.
37. ✅ **`seek(delta)`** — `prev_chunk / replay_chunk / next_chunk`
    each delegate to a single `seek(±1 / 0)`.
38. ✅ **Backend cache requested-name** — `_get_backend` caches
    against the requested engine name, so a Kokoro→Piper fallback
    doesn't keep reinstantiating every chunk.
39. ✅ **JSON corruption logging + `.bak`** — `load_config` and
    `load_history` rename the bad file to `.bak` and print to stderr
    instead of silently discarding.
40. ✅ **Public `is_paused` property** — added so future tests can
    check it without touching `_is_paused` privately.
41. ✅ **E701** — 0 remaining (was 57). Inline `try: x; except: pass`
    expanded to multi-line throughout.
42. ✅ **F401 / F841** — all unused imports / variables removed.
43. ✅ **`Image.LANCZOS` deprecation** — `tray.py` uses
    `getattr(Image, "Resampling", Image).LANCZOS` so it works on
    Pillow ≥ 9.1 without a DeprecationWarning.

---

## Deferred (3 items)

The three items above marked ⏳ are architectural cleanups that don't
fix an open bug:

- **#16 Player extraction** — engine is correct under one lock; the
  split would re-implement that lock for marginal SRP win.
- **#33 `ActionSpec`** — the worst duplication is gone; remaining
  hotkey-label work is cosmetic and lives in `app.py`.
- **#34 MOODS** — keeping mood tone metadata next to the voice id
  is intentional; voices can move freely between moods.

Pick any of these up if a future contributor wants to add a new TTS
backend (#16) or a 9th hotkey-driven action (#33).

---

## Tooling

`pytest`, `ruff`, `mypy` configured in the repo:

```text
pytest          152 passed in 6 s
ruff            0 errors
mypy            21 → ~12 errors remaining (all Tk overload noise)
```

Run them yourself:

```bash
python -m pytest -q
python -m ruff check pippal tests reader_app.py pippal_open.py
python -m mypy --ignore-missing-imports pippal
```
