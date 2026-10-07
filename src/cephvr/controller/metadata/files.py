"""E04 atomic publication and safe output path components."""

from __future__ import annotations

import os
import re
import sys
import uuid
from pathlib import Path

from cephvr.controller.metadata.types import StorageError


def sync_directory(path: Path) -> None:
    if sys.platform == "win32":
        raise StorageError("Windows directory durability helper unavailable")
    fd = os.open(path, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def atomic_json(path: Path, payload: bytes, *, replace: bool) -> None:
    temporary = path.with_name(f".cv-{uuid.uuid4().hex}.tmp")
    temporary_io = temporary
    if sys.platform == "win32":
        from cephvr.platform.windows.paths import extended_path

        temporary_io = Path(extended_path(temporary))
    try:
        with temporary_io.open("xb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        if sys.platform == "win32":
            from cephvr.platform.windows.durable import create_synced, replace_synced

            if replace:
                replace_synced(temporary, path)
            else:
                create_synced(temporary, path)
        else:
            if replace:
                os.replace(temporary, path)
            else:
                os.link(temporary, path, follow_symlinks=False)
            sync_directory(path.parent)
    finally:
        temporary_io.unlink(missing_ok=True)


def safe_component(value: str) -> str:
    normalized = re.sub(r"[^A-Za-z0-9_-]+", "_", value).strip("_")
    if not normalized or normalized in {".", ".."}:
        raise StorageError("experiment and subject require safe nonempty names")
    return normalized
