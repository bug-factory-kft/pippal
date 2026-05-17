# PySide6 / Qt licensing — migration spike

**Short version:** PipPal stays MIT. Qt (via PySide6) is LGPLv3. The
two are compatible **provided** Qt is dynamically linked (it is — it's
a normal Python import), users can replace the Qt libraries, the LGPL
licence texts ship with any binary distribution, and we do **not**
freeze the app into a single-file/onefile executable.

> Final legal sign-off is the team's call. This document records the
> engineering constraints the migration must respect so that the
> compliance decision is a review, not a rework.

## What licence each part is under

| Component | Licence | Notes |
|---|---|---|
| PipPal application code (incl. `pippal.ui_qt`) | **MIT** | Unchanged. `pyproject.toml` `license = "MIT"`. |
| PySide6 (the Qt for Python bindings) | **LGPLv3** | Also available under a commercial Qt licence; we rely on the LGPL option. |
| Qt 6 libraries shipped inside the PySide6 wheel | **LGPLv3** (with some modules GPL/commercial-only) | We only use core GUI/Widgets modules, which are LGPLv3. |
| Existing deps (`keyboard`, `pyperclip`, `pystray`, `Pillow`) | unchanged | Not affected by this spike. |

## Why MIT app + LGPL Qt is fine here

The LGPLv3 lets a proprietary-or-permissive application use the
library **as long as the end user can swap the library** for their own
build. Concretely, for PipPal:

1. **Dynamic linking only.** PySide6 is imported at runtime
   (`import PySide6...`). There is no static linking and no
   header-level inlining of Qt into MIT code. The MIT app and the
   LGPL library remain separate works that talk over the published
   PySide6 API. This is the LGPL's intended use mode.

2. **User can replace Qt.** In a directory-style distribution the Qt
   DLLs / `PySide6` package sit as ordinary files next to the app. A
   user can drop in their own compatible Qt build. We must keep it
   that way (see "Packaging constraints" below).

3. **Ship the LGPL licence texts.** Any binary distribution must
   include the LGPLv3 (and GPLv3, which LGPLv3 incorporates by
   reference) licence text plus the PySide6/Qt copyright and "this
   product uses Qt under the LGPLv3" notice. PipPal already has an
   open-source-notices surface (the **Open-source notices** settings
   card → `View licences…`, backed by `NOTICES.txt` /
   `docs/THIRD_PARTY.md`). The Qt/PySide6 LGPL block must be added to
   that notices file as part of productionising this spike. (Not done
   in this spike — it ships no binary.)

4. **State any Qt modifications.** We do not modify Qt or PySide6
   source. If that ever changes, the modified library source must be
   offered under the LGPL.

## Packaging constraints (the load-bearing rule)

**Do not produce a single-file / `--onefile` frozen executable.**

A onefile bundle (PyInstaller `--onefile`, Nuitka onefile, etc.)
embeds the Qt libraries inside an opaque self-extracting blob. That
defeats the LGPL "user can relink/replace the library" requirement and
makes compliance materially harder (you'd have to ship object files or
a documented relink path).

Use a **directory bundle** instead:

- PyInstaller **`--onedir`** (or Nuitka standalone, or a plain
  venv-style layout). The existing PipPal MSIX/onedir packaging note in
  `src/pippal/paths.py` already assumes a `--onedir` layout, so this
  matches how the Tk build is shipped today.
- Keep the `PySide6` package / Qt DLLs as discrete, replaceable files
  in the bundle directory.
- Include the LGPLv3 + GPLv3 texts and the Qt/PySide6 attribution in
  the shipped notices.

## Net effect on PipPal's own licence

Adding PySide6 as a runtime UI dependency does **not** force PipPal to
relicense. PipPal's source stays MIT and can be used under MIT terms.
The only obligations are distribution-time (ship licence texts, keep
Qt replaceable, no onefile freeze) — they constrain the **installer**,
not the source licence.

## TL;DR for reviewers

- App: MIT ✅ (no change)
- Qt: LGPLv3, dynamically linked via PySide6 import ✅
- Must ship: LGPLv3 + GPLv3 texts + Qt attribution in NOTICES ⚠️ (do
  when productionising)
- Must NOT: onefile freeze 🚫 — use `--onedir` directory bundle
- Final legal sign-off: **the team's**
