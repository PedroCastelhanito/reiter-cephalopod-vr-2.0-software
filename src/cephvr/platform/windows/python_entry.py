"""Run a managed CephVR module after registering its base Python DLL paths."""

from __future__ import annotations

import os
import runpy
import sys

from cephvr.platform.windows.python_runtime import resolve_python_runtime

_DLL_DIRECTORY_HANDLES: list[object] = []


def main() -> None:
    if len(sys.argv) < 2:
        raise SystemExit("usage: python_entry <module> [arguments...]")
    _, dll_directories = resolve_python_runtime()
    if hasattr(os, "add_dll_directory"):
        _DLL_DIRECTORY_HANDLES.extend(
            os.add_dll_directory(directory) for directory in dll_directories
        )
    module, *arguments = sys.argv[1:]
    sys.argv = [module, *arguments]
    runpy.run_module(module, run_name="__main__", alter_sys=True)


if __name__ == "__main__":
    main()
