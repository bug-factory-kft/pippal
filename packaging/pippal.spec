# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for PipPal (free edition) — one-click Windows installer.

Build with (from the repo root):

    pyinstaller --noconfirm packaging/pippal.spec

Produces ``dist/PipPal/`` (onedir layout).  The entire folder is what
gets wrapped into the Inno Setup installer by
``packaging/installer/pippal.iss``.

Layout assumptions:
- The free repo is checked out at ``<spec-dir>/..`` (i.e. Path.cwd()
  must be the repo root when PyInstaller is invoked).
- ``piper/piper.exe`` must be the REAL Piper binary (>=500 KB) before
  invoking PyInstaller.  Place it by:
  * copying from pippal-pro's dist/_internal/piper/, OR
  * downloading piper_windows_amd64.zip from rhasspy/piper 2023.11.14-2
    (the same URL used by setup.ps1) and extracting into ``piper/``.
  The CI workflow (release-installer.yml) performs the download
  automatically before calling PyInstaller.

Adapted from ``pippal-pro/packaging/pippal_pro.spec``.  Key differences:
- No Pro-only packages (no gruut/onnxruntime/pypdf/kokoro/soundfile).
- piper/ lives at the repo root, not in packaging/build/piper/.
- Icon is taken from assets/pippal_icon.ico (committed in the free repo).
- Packaged via Inno Setup, not MSIX/makeappx.
"""

from __future__ import annotations

import os as _os
from pathlib import Path

from PyInstaller.utils.hooks import (
    collect_data_files,
    collect_dynamic_libs,
    collect_submodules,
)

# PyInstaller sets SPECPATH to the directory containing this .spec file.
# Using SPECPATH (rather than Path.cwd()) allows PyInstaller to be invoked
# from any working directory — the repo root is always the parent of packaging/.
HERE = Path(SPECPATH)        # packaging/
REPO_ROOT = HERE.parent      # repo root

# Entry point: a thin launcher that delegates to pippal.web_ui.app_web.main.
ENTRY = str(HERE / "pippal_launch.py")

# Runtime assets bundled into the frozen dist.
PIPER_DIR = REPO_ROOT / "piper"
WEBUI_DIR = REPO_ROOT / "webui"
ASSETS_DIR = REPO_ROOT / "assets"

# Icon for the EXE — assets/pippal_icon.ico is committed in the free repo.
ICON_ICO = str(ASSETS_DIR / "pippal_icon.ico")

# ---------------------------------------------------------------------------
# datas
# ---------------------------------------------------------------------------
datas: list[tuple[str, str]] = []

# --- webui (ES6 static frontend) bundled at <_MEIPASS>/webui/ ----
# server.py's _resolve_webui_dir() prefers sys._MEIPASS/webui when frozen.
if WEBUI_DIR.exists():
    for src in WEBUI_DIR.rglob("*"):
        if src.is_file():
            rel = src.relative_to(WEBUI_DIR).parent
            datas.append((str(src), str(Path("webui") / rel)))

# --- assets/ (icon + onboarding WAVs) bundled at <_MEIPASS>/assets/ ---
# paths.py's _resolve_asset_path() prefers INSTALL_ROOT/assets when frozen
# (INSTALL_ROOT = sys._MEIPASS).
if ASSETS_DIR.exists():
    for src in ASSETS_DIR.rglob("*"):
        if src.is_file():
            rel = src.relative_to(ASSETS_DIR).parent
            datas.append((str(src), str(Path("assets") / rel)))

# --- piper engine: piper.exe + DLLs + espeak-ng-data ---
# Exclude the stub backup (.stub-bak) and pkgconfig/ (build-time only).
# paths.py's PIPER_DIR resolves to <_MEIPASS>/piper when frozen.
_PIPER_SKIP_NAMES = {"piper.exe.stub-bak", "pkgconfig"}
if PIPER_DIR.exists():
    for child in PIPER_DIR.iterdir():
        if child.name in _PIPER_SKIP_NAMES:
            continue
        if child.is_file():
            datas.append((str(child), "piper"))
        elif child.is_dir():
            for sub in child.rglob("*"):
                if sub.is_file():
                    rel = sub.relative_to(PIPER_DIR).parent
                    datas.append((str(sub), str(Path("piper") / rel)))

# --- third-party notices -------------------------------------------------
# notices.py::resolve_notices_path checks INSTALL_ROOT/"docs/THIRD_PARTY.md".
# INSTALL_ROOT == sys._MEIPASS when frozen (= dist/PipPal/_internal/), so we
# bundle the file into the "docs/" subdirectory inside _MEIPASS so the path
# INSTALL_ROOT/"docs/THIRD_PARTY.md" resolves correctly in the frozen app.
_NOTICES_SRC = REPO_ROOT / "docs" / "THIRD_PARTY.md"
if _NOTICES_SRC.exists():
    datas.append((str(_NOTICES_SRC), "docs"))

# --- pywebview data files ------------------------------------------------
# pywebview ships its own PyInstaller hook that pulls in the edgechromium
# backend's bundled WebView2 interop assemblies + WebView2Loader.dll on
# Windows.  collect_data_files picks up anything the hook may miss.
try:
    datas += collect_data_files("webview")
except Exception:
    pass

# --- winsdk projection metadata (for toast notifications) ----------------
try:
    datas += collect_data_files("winsdk")
except Exception:
    pass

# ---------------------------------------------------------------------------
# hiddenimports
# ---------------------------------------------------------------------------
# pywebview picks its platform backend at runtime via importlib; PyInstaller
# can't follow that statically.  We mirror Pro's spec exactly for the
# edgechromium/WebView2 + winsdk toast stack.
hiddenimports: list[str] = (
    collect_submodules("pippal")
    # pywebview: all backends + explicit edgechromium/winforms + pythonnet bridge
    + collect_submodules("webview")
    + [
        "clr",
        "clr_loader",
        "webview.platforms.edgechromium",
        "webview.platforms.winforms",
    ]
    # winsdk: namespace-package walk (collect_submodules stops at top-level;
    # descend via winsdk.windows which has real __init__.py children).
    + collect_submodules("winsdk.windows")
    + [
        "winsdk._winrt",
        "winsdk.windows.data.xml.dom",
        "winsdk.windows.ui.notifications",
    ]
    # Tray + hotkeys + clipboard + icon rendering
    + [
        "pystray",
        "keyboard",
        "pyperclip",
        "PIL",
        "PIL.Image",
        "PIL.ImageDraw",
        "PIL.ImageFont",
    ]
)

# ---------------------------------------------------------------------------
# binaries
# ---------------------------------------------------------------------------
# pythonnet's CLR runtime + clr_loader's native shim back the edgechromium
# backend's .NET interop in frozen mode.
binaries: list[tuple[str, str]] = []
for _pkg in ("clr_loader", "pythonnet"):
    try:
        binaries += collect_dynamic_libs(_pkg)
    except Exception:
        pass

# ---------------------------------------------------------------------------
# Analysis
# ---------------------------------------------------------------------------
a = Analysis(
    [ENTRY],
    pathex=[str(REPO_ROOT / "src")],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # Test runner — not shipped.
        "pytest",
        "_pytest",
        # Tk UI was removed; excluding here makes any residual Tk import fail
        # loudly at build time rather than silently at runtime.
        "tkinter",
        "_tkinter",
        "Tkinter",
        # Non-Windows pywebview backends — dead weight on Windows.
        "PyQt5",
        "PyQt6",
        "PySide2",
        "PySide6",
        "gi",
        "webview.platforms.qt",
        "webview.platforms.gtk",
        "webview.platforms.cocoa",
    ],
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="PipPal",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,   # tray app — no cmd window
    icon=ICON_ICO if Path(ICON_ICO).exists() else None,
    disable_windowed_traceback=False,
    target_arch="x64",
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="PipPal",
)
