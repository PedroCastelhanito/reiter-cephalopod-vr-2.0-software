"""Extended path spelling for Windows APIs that do not inherit Python policy."""

from __future__ import annotations

import os
from pathlib import Path


def extended_path(path: Path | str) -> str:
    """Return an absolute path using Win32's extended-length namespace."""
    value = os.path.abspath(os.fspath(path))
    if value.casefold().startswith("\\\\?\\"):
        return value
    if value.startswith("\\\\"):
        return "\\\\?\\UNC\\" + value[2:]
    return "\\\\?\\" + value


def logical_path(path: Path | str) -> str:
    """Strip Win32's extended-length transport prefix for stable identities."""
    value = os.path.abspath(os.fspath(path))
    if value.casefold().startswith("\\\\?\\unc\\"):
        return "\\\\" + value[8:]
    if value.casefold().startswith("\\\\?\\"):
        return value[4:]
    return value
