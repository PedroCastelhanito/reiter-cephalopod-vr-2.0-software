#!/usr/bin/env python3
"""Start the local GUI using the repository environment, from any directory."""

import argparse
import os
import subprocess
import sys
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Open the CephVR GUI with local review controls; no hardware is started."
    )
    parser.add_argument(
        "--read-only",
        action="store_true",
        help="Open the disconnected frontend without sample data or review controls.",
    )
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    python = (
        root / ".venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    )
    if not python.is_file():
        print(
            f"Project Python environment not found: {python}\n"
            "Follow docs/development.md to create .venv and install the GUI dependencies.",
            file=sys.stderr,
        )
        return 1
    command = [str(python), "-m", "cephvr.gui.review"]
    if not args.read_only:
        command.append("--review")
    try:
        return subprocess.call(command, cwd=root)
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
