#!/usr/bin/env python3
"""Start the simulated design-review GUI from any directory."""

import os
import subprocess
import sys
from pathlib import Path


def main() -> int:
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
    command = [
        str(python),
        "-m",
        "cephvr.gui.review",
        "--review",
        "--simulated-devices",
    ]
    try:
        return subprocess.call(command, cwd=root)
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
