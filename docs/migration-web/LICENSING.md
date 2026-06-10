# Web-UI migration — licensing summary

This is an engineering summary to support review. **Final legal
sign-off is the team's**, not this document's.

## App licence — unchanged

PipPal stays **MIT** (`LICENSE.md`, `pyproject.toml: license = "MIT"`).
This migration adds a parallel frontend; it does not relicense the app
and does not vendor third-party source into the package.

## Runtime dependency added (ships with the app)

| Component | Licence | Role | Distribution impact |
|-----------|---------|------|---------------------|
| **pywebview** | **BSD-3-Clause** | Hosts the local HTML/CSS/JS UI in a native window and bridges JS↔Python | Permissive; BSD-3 is MIT-compatible. Attribution required in notices. |
| **WebView2 runtime** (Microsoft Edge WebView2, Chromium) | Microsoft proprietary runtime, redistributable under the [WebView2 SDK / Distribution terms](https://developer.microsoft.com/microsoft-edge/webview2/) | The actual browser engine pywebview drives on Windows | Not bundled by PipPal. WebView2 is **pre-installed on Windows 11** and on most Windows 10; pywebview uses the system runtime. If a packaged build needs to guarantee it, ship the Microsoft **Evergreen Bootstrapper** per Microsoft's redistribution terms — that is a packaging/legal decision for the team, not changed here. |

The existing native pieces are unchanged and keep their current
licences: **pystray** (LGPL-3.0-or-later, used unmodified as a
library — system tray), **keyboard** (MIT — global hotkeys),
**Pillow** (MIT-CMU), Piper + voices (their own licences, unchanged).

## Test-only dependency (does NOT ship)

| Component | Licence | Role |
|-----------|---------|------|
| **Playwright (Python)** | **Apache-2.0** | E2E browser automation in `e2e/web/` |
| pytest, pytest-playwright | MIT / Apache-2.0 | test runner / fixtures |

Playwright and its bundled Chromium are dev/test only (`e2e/web/
requirements.txt`). They are never imported by the app and never
packaged into a release artifact, so they impose no obligation on the
shipped product beyond the existing dev toolchain.

## Notes for the legal reviewer

- BSD-3 (pywebview) + MIT (app) compose cleanly; add the pywebview
  copyright/licence line to the bundled `NOTICES.txt` / `THIRD_PARTY.md`
  when this frontend is promoted past spike status.
- WebView2 is the only non-OSS runtime touchpoint. The dependency is
  *on a Microsoft system component*, comparable to depending on the OS.
  Decide bundling strategy (rely on system runtime vs. ship the
  Evergreen bootstrapper) during productization.
- Apache-2.0 has a patent grant and NOTICE-propagation clause, but
  because Playwright is test-only those clauses do not reach the
  distributed product.
- No GPL/AGPL code is introduced by this migration. (pystray's LGPL was
  already present and is used as an unmodified dynamically-imported
  library.)
