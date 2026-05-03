"""Named timing constants — magic-numbers consolidated in one place
so readers don't have to guess what 0.04 / 0.05 / 60 / 1800 mean."""

from __future__ import annotations

# ----- engine playback -----
# Time the playback wait-loop sleeps between cancellation polls.
PLAYBACK_POLL_S: float = 0.04
# Extra padding added to the end-of-chunk deadline so winsound has a
# chance to finish flushing before we delete the WAV.
CHUNK_DEADLINE_PAD_S: float = 0.05
# Pause-loop sleep — slightly longer than the playback poll because
# nothing is moving while paused.
PAUSE_POLL_S: float = 0.08
# Best-effort wait on a prefetch thread at cancel-exit. Long enough for
# a normal subprocess.run to finish flushing, short enough that Stop
# still feels instant. A pathological hung prefetch (synth >2s past
# Stop) will leak its wav to TEMP_DIR until process restart.
PREFETCH_DRAIN_S: float = 2.0

# ----- selection capture -----
# How long to wait for the foreground app to populate the clipboard
# after we send Ctrl+C.
CLIPBOARD_READ_DEADLINE_S: float = 0.6
# Pause between modifier release and Ctrl+C send so the OS sees them
# as separate events.
CLIPBOARD_RELEASE_GAP_S: float = 0.04
# Inner poll for the clipboard while we wait for it to change.
CLIPBOARD_POLL_S: float = 0.03

# ----- overlay -----
# Time between animation frames in the reader panel (~16 fps).
OVERLAY_FRAME_MS: int = 60
# Lower bound on the auto-hide delay so a flash of "done" can still
# be read; upper bound comes from user config.
OVERLAY_HIDE_MIN_MS: int = 300
# How long a one-shot message ("Saved: …", "No selection") stays
# visible before the overlay self-dismisses.
OVERLAY_MESSAGE_MS: int = 1800

# ----- tray -----
# Period of the tray-icon idle/speaking poll. The engine state can
# change between ticks; the icon updates lazily.
TRAY_POLL_MS: int = 400

# ----- network -----
# Streaming download timeout for Voice Manager (Hugging Face) and
# the Kokoro installer.
DOWNLOAD_TIMEOUT_S: float = 30.0
# Per-call timeout for Ollama list_models — 3 s is enough for the
# UI to feel snappy while the daemon is local.
OLLAMA_LIST_TIMEOUT_S: float = 3.0
# Per-call timeout for Ollama chat completions; intentionally generous
# so a slow first-token doesn't kill a translate.
OLLAMA_CHAT_TIMEOUT_S: float = 180.0
