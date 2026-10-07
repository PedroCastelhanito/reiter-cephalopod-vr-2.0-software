#!/usr/bin/env python3
"""Start the managed Windows runtime, including its controller-backed GUI."""

import argparse
import os
import subprocess
import sys
from pathlib import Path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--reopen-gui",
        action="store_true",
        help="open a fresh GUI in the running application generation",
    )
    args = parser.parse_args(argv)
    root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(root / "src"))
    from cephvr.launcher.entrypoint import launcher_command

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
    command = launcher_command(root, python, reopen_gui=args.reopen_gui)
    try:
        return subprocess.call(command, cwd=root)
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
