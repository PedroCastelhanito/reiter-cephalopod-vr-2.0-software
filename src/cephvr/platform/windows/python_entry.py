"""Run a managed CephVR module after registering its base Python DLL paths."""

from __future__ import annotations

import importlib
import os
import runpy
import sys
from collections.abc import Callable
from types import ModuleType

from cephvr.platform.windows.python_runtime import (
    PythonRuntimeError,
    resolve_python_runtime,
)

_DLL_DIRECTORY_HANDLES: list[object] = []


def accelerate_hashlib(
    hashlib: ModuleType | None = None,
    reload: Callable[[ModuleType], ModuleType] = importlib.reload,
) -> None:
    """Rebind hashlib to OpenSSL once base DLL paths make `_hashlib` importable.

    Runtime validation imports hashlib before those paths exist, leaving the
    builtin `_sha256` fallback, which holds the GIL across large digests and
    stalls the render thread. Refuse to run managed modules on that fallback.
    """
    if hashlib is None:
        hashlib = importlib.import_module("hashlib")
    if hashlib.sha256.__module__ != "_hashlib":
        hashlib = reload(hashlib)
    if hashlib.sha256.__module__ != "_hashlib":
        raise PythonRuntimeError(
            "managed Python hashlib lacks the OpenSSL provider after DLL "
            f"registration (sha256 from {hashlib.sha256.__module__})"
        )


def main() -> None:
    if len(sys.argv) < 2:
        raise SystemExit("usage: python_entry <module> [arguments...]")
    _, dll_directories = resolve_python_runtime()
    if hasattr(os, "add_dll_directory"):
        _DLL_DIRECTORY_HANDLES.extend(
            os.add_dll_directory(directory) for directory in dll_directories
        )
    accelerate_hashlib()
    module, *arguments = sys.argv[1:]
    sys.argv = [module, *arguments]
    runpy.run_module(module, run_name="__main__", alter_sys=True)


if __name__ == "__main__":
    main()
