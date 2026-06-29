"""Centralised filesystem paths and runtime constants.

Two roots:

- ``INSTALL_ROOT`` is where the package is installed/extracted from
  (the source checkout in dev, ``Program Files\\WindowsApps\\…`` under
  MSIX). Read-only under MSIX. Holds the bundled engine binary and
  static assets.
- ``DATA_ROOT`` is where runtime/user state lives — voices the user
  installs, config, history, scratch files. Always under
  ``%LOCALAPPDATA%\\PipPal`` so dev and packaged builds behave the same
  and we never try to write into the install dir.

``DATA_ROOT`` can be overridden via the ``PIPPAL_DATA_DIR`` env var
so test fixtures can redirect into ``tmp_path`` without touching the
real profile."""

from __future__ import annotations

import os
import sys
from pathlib import Path


# ---- Install root (read-only-safe) -----------------------------------
def _resolve_install_root() -> Path:
    """Where the bundled engine binary and static assets live.

    PyInstaller ``--onedir`` puts ``datas`` under ``_internal/``;
    ``sys._MEIPASS`` points at that ``_internal/`` dir at runtime, so
    ``INSTALL_ROOT/assets/...`` and ``INSTALL_ROOT/piper/...`` resolve
    correctly inside the MSIX bundle.

    In dev (no frozen build) ``__file__`` is ``…/src/pippal/paths.py``,
    so the ``src`` layout points back to the source checkout root. In
    a normal package install, ``__file__`` is ``…/site-packages/pippal``
    and package data lives next to the module itself."""
    if getattr(sys, "frozen", False):
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass:
            return Path(meipass)
    package_root = Path(__file__).resolve().parent
    source_root = _source_checkout_root(package_root)
    return source_root if source_root is not None else package_root


def _source_checkout_root(package_root: Path) -> Path | None:
    src_root = package_root.parent
    if src_root.name != "src":
        return None
    checkout = src_root.parent
    if (checkout / "pyproject.toml").exists():
        return checkout
    return None


INSTALL_ROOT: Path = _resolve_install_root()
PACKAGE_ROOT: Path = Path(__file__).resolve().parent


def _resolve_asset_path(*parts: str) -> Path:
    install_asset = INSTALL_ROOT / "assets" / Path(*parts)
    if install_asset.exists():
        return install_asset
    return PACKAGE_ROOT / "assets" / Path(*parts)


# Bundled engine binary + static assets — the install layer is allowed
# to be read-only.
PIPER_DIR: Path = INSTALL_ROOT / "piper"
PIPER_EXE: Path = PIPER_DIR / "piper.exe"
ASSET_ICON_PATH: Path = _resolve_asset_path("pippal_icon.png")

# Pre-recorded onboarding clip played when the user triggers a Read /
# Queue action and no engine is ready (no voice installed). Tells the
# user how to install a voice — without needing a working TTS to do it.
ASSET_NO_VOICE_WAV: Path = _resolve_asset_path("onboarding", "pippal-no-installed-language.wav")


# ---- Data root (always writable) -------------------------------------


def _get_current_package_full_name() -> str | None:
    """Return the MSIX package full name via ctypes, or None.

    Safe on every platform: the WinDLL load is guarded; returns None on
    Linux/macOS/CI and when the process is unpackaged
    (APPMODEL_ERROR_NO_PACKAGE = 15700).  Never raises.
    """
    try:
        import ctypes

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        fn = kernel32.GetCurrentPackageFullName
        fn.argtypes = [ctypes.POINTER(ctypes.c_uint32), ctypes.c_wchar_p]
        fn.restype = ctypes.c_long
        length = ctypes.c_uint32(0)
        rc = fn(ctypes.byref(length), None)
        if rc == 15700:  # APPMODEL_ERROR_NO_PACKAGE — running unpackaged
            return None
        buf = ctypes.create_unicode_buffer(length.value)
        rc = fn(ctypes.byref(length), buf)
        if rc != 0:
            return None
        return buf.value or None
    except Exception:
        return None


def _package_family_name(full_name: str) -> str | None:
    """Derive PackageFamilyName from a PackageFullName.

    PackageFullName format:
        <Name>_<Version>_<Arch>_<ResourceId>_<PublisherHash>

    PackageFamilyName is the first component (Name) plus the last
    component (PublisherHash), joined by ``_``:
        <Name>_<PublisherHash>

    Returns None when the full name cannot be parsed.
    """
    parts = full_name.split("_")
    # Minimum valid full name has 5 parts: name, version, arch, resourceid, hash
    if len(parts) < 5:
        return None
    name = parts[0]
    publisher_hash = parts[-1]
    if not name or not publisher_hash:
        return None
    return f"{name}_{publisher_hash}"


def _packaged_local_appdata_root() -> Path | None:
    """Return the container-redirected LocalAppData root when packaged, else None.

    Under MSIX the OS silently redirects ``%LOCALAPPDATA%`` writes to
    ``%LOCALAPPDATA%\\Packages\\<PackageFamilyName>\\LocalCache\\Local``.
    This function resolves that explicit path so that both in-container
    writers and out-of-container callers (e.g. Explorer) agree on one
    canonical location.

    Returns None (never raises) when:
    - Not running on Windows.
    - The process has no package identity (running unpackaged / in dev).
    - The package full name cannot be parsed.
    - Any error occurs.
    """
    try:
        full_name = _get_current_package_full_name()
        if full_name is None:
            return None
        family_name = _package_family_name(full_name)
        if family_name is None:
            return None
        local_appdata = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~/AppData/Local")
        return Path(local_appdata) / "Packages" / family_name / "LocalCache" / "Local"
    except Exception:
        return None


def _resolve_data_root() -> Path:
    # 1. Explicit override wins (test fixtures, dev overrides).
    override = os.environ.get("PIPPAL_DATA_DIR")
    if override:
        return Path(override)
    # 2. Under MSIX packaged identity: use the container-redirected path so
    #    that both in-container writers and out-of-container callers (Explorer)
    #    resolve to the same canonical directory.
    packaged_root = _packaged_local_appdata_root()
    if packaged_root is not None:
        return packaged_root / "PipPal"
    # 3. Unpackaged / dev / Linux / CI: plain %LOCALAPPDATA%\PipPal.
    local_appdata = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~/AppData/Local")
    return Path(local_appdata) / "PipPal"


DATA_ROOT: Path = _resolve_data_root()

VOICES_DIR: Path = DATA_ROOT / "voices"
CONFIG_PATH: Path = DATA_ROOT / "config.json"
HISTORY_PATH: Path = DATA_ROOT / "history.json"
TEMP_DIR: Path = DATA_ROOT / "temp"

# Local IPC for the right-click context menu and external integrations.
CMD_SERVER_PORT: int = 51677

# Persisted port file: the running instance writes the actually-bound port
# here so a second startup can connect-first (instead of guessing 51677).
CMD_PORT_FILE: Path = DATA_ROOT / ".cmd_port"


def ensure_dirs() -> None:
    """Create runtime-required directories if they don't exist yet.
    Engine extensions are responsible for creating their own
    directories at registration time."""
    for d in (DATA_ROOT, TEMP_DIR, VOICES_DIR):
        d.mkdir(parents=True, exist_ok=True)
