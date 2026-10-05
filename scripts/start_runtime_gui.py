#!/usr/bin/env python3
"""Start the managed Windows runtime, including its controller-backed GUI."""

import os
import subprocess
import sys
from pathlib import Path


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    if os.name != "nt":
        print("The managed runtime GUI requires Windows.", file=sys.stderr)
        return 1
    python = root / ".venv" / "Scripts" / "python.exe"
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
        "cephvr.launcher.main",
        "--software-root",
        str(root),
        "--supervisor-config",
        str(root / "config" / "backends" / "supervisor_config.toml"),
        "--python",
        str(python),
    ]
    try:
        return subprocess.call(command, cwd=root)
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
