"""Same-directory Windows write-through publication for E04 metadata files."""

from __future__ import annotations

import ctypes
import sys
from ctypes import wintypes
from pathlib import Path

from cephvr.platform.windows.jobs import WindowsLaunchError

MOVEFILE_REPLACE_EXISTING = 0x1
MOVEFILE_WRITE_THROUGH = 0x8


def _move(source: Path, destination: Path, *, replace: bool) -> None:
    if sys.platform != "win32":
        raise WindowsLaunchError("Windows metadata publication requires Windows")
    source, destination = Path(source), Path(destination)
    if source.parent.resolve(strict=True) != destination.parent.resolve(strict=True):
        raise ValueError("metadata publication must remain in one directory")
    if source.is_symlink() or destination.is_symlink():
        raise ValueError("metadata publication cannot follow a symlink")
    if not source.is_file():
        raise ValueError("synced source file does not exist")
    api = ctypes.WinDLL("kernel32", use_last_error=True)
    api.MoveFileExW.argtypes = [wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.DWORD]
    api.MoveFileExW.restype = wintypes.BOOL
    flags = MOVEFILE_WRITE_THROUGH | (MOVEFILE_REPLACE_EXISTING if replace else 0)
    if not api.MoveFileExW(str(source), str(destination), flags):
        raise WindowsLaunchError(
            f"MoveFileExW write-through publication failed: {ctypes.get_last_error()}"
        )


def replace_synced(source: Path, destination: Path) -> None:
    """Publish a previously synced temp file over an existing metadata file."""
    _move(source, destination, replace=True)


def create_synced(source: Path, destination: Path) -> None:
    """Publish a previously synced temp file, refusing an existing destination."""
    _move(source, destination, replace=False)
