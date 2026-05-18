"""Per-journey **recording** for the Tier-2 user-journey suite.

==========================================================================
WHY THIS EXISTS / THE HONEST connect_over_cdp CONSTRAINT
==========================================================================

The Tier-2 journeys attach to an **already-running** WebView2 desktop
window via Playwright ``chromium.connect_over_cdp``. We did **not**
launch that browser ourselves (the real ``app_web.main()`` /
pywebview / WebView2 did), so Playwright's *native* recording knobs
do **not** work here:

* ``browser.new_context(record_video_dir=...)`` / the pytest-playwright
  ``--video`` flag only record contexts/pages **Playwright itself
  launched**. Over ``connect_over_cdp`` to a foreign browser there is
  no Playwright-owned context to attach a video sink to, so a native
  ``.webm`` is never produced. This is a real, documented Playwright
  limitation of the CDP-attach mode — not something we can flag our
  way around.

So this module produces the two recordings that *do* work over a
foreign-CDP attachment:

1. **Playwright trace per journey** — ``context.tracing.start(...)``
   with ``screenshots=True, snapshots=True`` around the journey, then
   ``tracing.stop(path=trace.zip)``. A trace **does** work over
   ``connect_over_cdp`` (it instruments the page via CDP, it does not
   need a Playwright-launched browser). It is a fully scrubbable
   "recording": a timeline of every action with a DOM snapshot +
   screenshot at each step, opened with
   ``playwright show-trace <trace.zip>``. This is the closest thing to
   a real recording that the CDP-attach mode allows.

2. **A real screen/window video** — captured **out of band** from
   Playwright:

   * **Preferred:** ``ffmpeg -f gdigrab`` recording the actual desktop
     (the real PipPal WebView2 window is on the visible interactive
     session), started before the journey body and stopped after →
     one ``<journey>.mp4`` of the genuine window.
   * **Fallback (no ffmpeg):** a background thread grabs frames with
     ``page.screenshot`` on a fixed interval for the duration of the
     journey. If ffmpeg later turns out to be present those frames are
     muxed into ``<journey>.mp4``; otherwise we keep the numbered
     ``frames/`` PNGs **and** assemble a single dense contact-sheet
     ``<journey>.frames.png`` strip so there is still a visual
     time-lapse "recording" of the run.

Every capture path is **best-effort and non-fatal**: any failure to
start/stop a recorder is swallowed and must never fail the journey.
"""

from __future__ import annotations

import math
import os
import shutil
import subprocess
import threading
import time
from pathlib import Path
from typing import Any


def _which_ffmpeg() -> str | None:
    """Resolve an ``ffmpeg`` executable.

    Checks ``PATH`` first, then a few common Windows install locations
    (winget links / Chocolatey / a manual ``C:\\ffmpeg``). Returns the
    path or ``None`` if ffmpeg is genuinely unavailable on this host
    (in which case the screenshot-strip fallback is used).
    """
    found = shutil.which("ffmpeg")
    if found:
        return found
    candidates = [
        Path(os.environ.get("LOCALAPPDATA", ""))
        / "Microsoft"
        / "WinGet"
        / "Links"
        / "ffmpeg.exe",
        Path(r"C:\ProgramData\chocolatey\bin\ffmpeg.exe"),
        Path(r"C:\ffmpeg\bin\ffmpeg.exe"),
        Path(r"C:\Program Files\ffmpeg\bin\ffmpeg.exe"),
    ]
    for c in candidates:
        try:
            if c and c.is_file():
                return str(c)
        except Exception:
            continue
    return None


class JourneyRecorder:
    """Record ONE journey: a Playwright trace + a screen/window video.

    Usage (already wired by ``conftest.py``'s ``real_app`` fixture)::

        rec = JourneyRecorder(out_dir, name)
        rec.start(context, page)        # before the journey body
        ...                             # the journey runs
        rec.stop(context, page)         # after — writes trace.zip + .mp4

    Construction never raises; ``start``/``stop`` swallow every error so
    a recording problem can never fail the journey under test.
    """

    #: Frame cadence (Hz) for the no-ffmpeg screenshot fallback.
    FALLBACK_FPS = 2

    def __init__(self, out_dir: Path, name: str) -> None:
        self._dir = Path(out_dir)
        self._name = name
        self._trace_path = self._dir / f"{name}.trace.zip"
        self._video_path = self._dir / f"{name}.mp4"
        self._frames_dir = self._dir / f"{name}.frames"
        self._strip_path = self._dir / f"{name}.frames.png"
        self._ffmpeg = _which_ffmpeg()
        self._ff_proc: subprocess.Popen | None = None
        self._tracing_ctx: Any = None
        self._grab_stop = threading.Event()
        self._grab_thread: threading.Thread | None = None
        self._grab_page: Any = None
        self._notes: list[str] = []

    # -- public API ----------------------------------------------------

    @property
    def notes(self) -> list[str]:
        """Human-readable record of exactly what was captured + how."""
        return list(self._notes)

    def start(self, context: Any, page: Any) -> None:
        try:
            self._dir.mkdir(parents=True, exist_ok=True)
        except Exception:
            pass
        self._start_trace(context)
        self._start_video(page)

    def stop(self, context: Any, page: Any) -> None:
        # Stop the video first so the trace's own stop work is not
        # captured into the journey recording.
        self._stop_video()
        self._stop_trace(context)

    # -- trace ---------------------------------------------------------

    def _start_trace(self, context: Any) -> None:
        if context is None:
            self._notes.append("trace: skipped (no CDP context)")
            return
        try:
            context.tracing.start(
                title=self._name,
                screenshots=True,
                snapshots=True,
                sources=False,
            )
            self._tracing_ctx = context
            self._notes.append("trace: started (screenshots+snapshots)")
        except Exception as exc:  # non-fatal
            self._tracing_ctx = None
            self._notes.append(f"trace: start failed ({exc!r})")

    def _stop_trace(self, context: Any) -> None:
        ctx = self._tracing_ctx if self._tracing_ctx is not None else context
        if ctx is None:
            return
        try:
            ctx.tracing.stop(path=str(self._trace_path))
            self._notes.append(
                f"trace: stopped -> {self._trace_path.name} "
                f"({self._size(self._trace_path)})"
            )
        except Exception as exc:  # non-fatal
            self._notes.append(f"trace: stop failed ({exc!r})")

    # -- video: ffmpeg gdigrab (preferred) -----------------------------

    def _start_video(self, page: Any) -> None:
        if self._ffmpeg:
            self._start_ffmpeg_gdigrab()
            if self._ff_proc is not None:
                return
            # ffmpeg present but failed to start → fall through to the
            # screenshot grabber so we still get a recording.
        self._start_screenshot_grabber(page)

    def _start_ffmpeg_gdigrab(self) -> None:
        # Capture the whole visible desktop (the real PipPal WebView2
        # window is on it). gdigrab cannot reliably target a borderless
        # pywebview window by title across WebView2 versions, so we grab
        # the full desktop — the journey window is the foreground app.
        try:
            cmd = [
                self._ffmpeg,
                "-y",
                "-loglevel",
                "error",
                "-f",
                "gdigrab",
                "-framerate",
                "10",
                "-i",
                "desktop",
                "-pix_fmt",
                "yuv420p",
                "-vcodec",
                "libx264",
                "-preset",
                "ultrafast",
                str(self._video_path),
            ]
            self._ff_proc = subprocess.Popen(
                cmd,
                stdin=subprocess.PIPE,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            self._notes.append(
                f"video: ffmpeg gdigrab started (pid {self._ff_proc.pid})"
            )
        except Exception as exc:  # non-fatal
            self._ff_proc = None
            self._notes.append(f"video: ffmpeg start failed ({exc!r})")

    def _stop_ffmpeg(self) -> None:
        proc = self._ff_proc
        if proc is None:
            return
        try:
            # 'q' on stdin asks ffmpeg to finalise the mp4 cleanly.
            try:
                if proc.stdin:
                    proc.stdin.write(b"q")
                    proc.stdin.flush()
            except Exception:
                pass
            try:
                proc.wait(timeout=10)
            except Exception:
                proc.terminate()
                try:
                    proc.wait(timeout=5)
                except Exception:
                    proc.kill()
            if self._video_path.exists():
                self._notes.append(
                    f"video: ffmpeg gdigrab -> {self._video_path.name} "
                    f"({self._size(self._video_path)})"
                )
            else:
                self._notes.append("video: ffmpeg produced no file")
        except Exception as exc:  # non-fatal
            self._notes.append(f"video: ffmpeg stop failed ({exc!r})")
        finally:
            self._ff_proc = None

    # -- video: screenshot grabber fallback ----------------------------

    def _start_screenshot_grabber(self, page: Any) -> None:
        if page is None:
            self._notes.append(
                "video: skipped (no ffmpeg and no page to grab)"
            )
            return
        try:
            self._frames_dir.mkdir(parents=True, exist_ok=True)
        except Exception:
            pass
        self._grab_page = page
        self._grab_stop.clear()
        self._grab_thread = threading.Thread(
            target=self._grab_loop, name=f"jrec-{self._name}", daemon=True
        )
        self._grab_thread.start()
        why = "no ffmpeg on host" if not self._ffmpeg else "ffmpeg unavailable"
        self._notes.append(
            f"video: screenshot grabber started ({why}; "
            f"{self.FALLBACK_FPS} fps page.screenshot)"
        )

    def _grab_loop(self) -> None:
        period = 1.0 / float(self.FALLBACK_FPS)
        idx = 0
        while not self._grab_stop.is_set():
            t0 = time.time()
            try:
                self._grab_page.screenshot(
                    path=str(self._frames_dir / f"f{idx:05d}.png"),
                    timeout=4000,
                )
                idx += 1
            except Exception:
                # The page may have navigated / a new window opened mid
                # journey; just skip this frame and keep going.
                pass
            dt = time.time() - t0
            self._grab_stop.wait(max(0.0, period - dt))

    def _stop_screenshot_grabber(self) -> None:
        if self._grab_thread is None:
            return
        self._grab_stop.set()
        try:
            self._grab_thread.join(timeout=10)
        except Exception:
            pass
        self._grab_thread = None
        try:
            frames = sorted(self._frames_dir.glob("f*.png"))
        except Exception:
            frames = []
        if not frames:
            self._notes.append("video: screenshot grabber captured 0 frames")
            return
        self._notes.append(
            f"video: screenshot grabber captured {len(frames)} frames "
            f"-> {self._frames_dir.name}/"
        )
        # If ffmpeg is present, mux the frames into a real .mp4.
        if self._ffmpeg:
            self._frames_to_mp4(frames)
        # Always also assemble a single dense contact-sheet strip so the
        # recording is viewable without ffmpeg or a frames browser.
        self._frames_to_strip(frames)

    def _frames_to_mp4(self, frames: list[Path]) -> None:
        try:
            cmd = [
                self._ffmpeg,
                "-y",
                "-loglevel",
                "error",
                "-framerate",
                str(self.FALLBACK_FPS),
                "-i",
                str(self._frames_dir / "f%05d.png"),
                "-pix_fmt",
                "yuv420p",
                "-vcodec",
                "libx264",
                "-preset",
                "ultrafast",
                str(self._video_path),
            ]
            subprocess.run(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=120,
                check=False,
            )
            if self._video_path.exists():
                self._notes.append(
                    f"video: frames muxed -> {self._video_path.name} "
                    f"({self._size(self._video_path)})"
                )
        except Exception as exc:  # non-fatal
            self._notes.append(f"video: frame mux failed ({exc!r})")

    def _frames_to_strip(self, frames: list[Path]) -> None:
        """Assemble a dense contact-sheet PNG of the journey frames.

        Pure stdlib + Pillow if available; if Pillow is missing we just
        keep the numbered frames (still a real visual recording).
        """
        try:
            from PIL import Image  # type: ignore
        except Exception:
            self._notes.append(
                "video: Pillow absent — kept numbered frames as the "
                "recording (no contact-sheet)"
            )
            return
        try:
            # Cap the strip so a long journey does not make a giant
            # image; sample evenly across the whole run.
            max_cells = 60
            if len(frames) > max_cells:
                step = len(frames) / float(max_cells)
                picked = [
                    frames[int(i * step)] for i in range(max_cells)
                ]
            else:
                picked = frames
            thumbs = []
            tw = 320
            for fp in picked:
                try:
                    im = Image.open(fp)
                    im.load()
                    ratio = tw / float(im.width or tw)
                    th = max(1, int((im.height or tw) * ratio))
                    thumbs.append(im.resize((tw, th)))
                except Exception:
                    continue
            if not thumbs:
                return
            cols = min(6, len(thumbs))
            rows = math.ceil(len(thumbs) / cols)
            cell_h = max(t.height for t in thumbs)
            sheet = Image.new(
                "RGB", (cols * tw, rows * cell_h), (16, 16, 16)
            )
            for i, t in enumerate(thumbs):
                r, c = divmod(i, cols)
                sheet.paste(t, (c * tw, r * cell_h))
            sheet.save(self._strip_path)
            self._notes.append(
                f"video: contact-sheet -> {self._strip_path.name} "
                f"({len(thumbs)} cells, {self._size(self._strip_path)})"
            )
        except Exception as exc:  # non-fatal
            self._notes.append(f"video: contact-sheet failed ({exc!r})")

    def _stop_video(self) -> None:
        if self._ff_proc is not None:
            self._stop_ffmpeg()
        else:
            self._stop_screenshot_grabber()

    # -- misc ----------------------------------------------------------

    @staticmethod
    def _size(p: Path) -> str:
        try:
            n = float(p.stat().st_size)
        except Exception:
            return "0 B"
        for unit in ("B", "KB", "MB", "GB"):
            if n < 1024.0 or unit == "GB":
                if unit == "B":
                    return f"{int(n)} {unit}"
                return f"{n:.1f} {unit}"
            n /= 1024.0
        return f"{n:.1f} GB"
