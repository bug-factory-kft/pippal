"""Tiny client invoked by Windows shell when right-clicking a file →
'Read with PipPal'. Sends the file path to the running PipPal instance."""

from __future__ import annotations

import sys
from pathlib import Path

src_dir = Path(__file__).resolve().parent / "src"
if src_dir.is_dir():
    sys.path.insert(0, str(src_dir))


def main() -> int:
    if len(sys.argv) < 2:
        return 1
    from pippal.open_file import main as real_main

    return real_main()


if __name__ == "__main__":
    sys.exit(main())
