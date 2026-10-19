"""Preflight the exact session tree before explicit destructive E04 recovery."""

from __future__ import annotations

import stat
from pathlib import Path

from cephvr.controller.metadata.types import StorageError
from cephvr.shared.clock import host_time_ns


def delete_contents(session: Path, deadline_ns: int) -> None:
    """Delete only regular descendants of the two displayed session namespaces.

    The caller retains the reservation guard and verifies the original marker.
    Reject links/reparse points and unexpected root entries before any deletion.
    """

    def check(path: Path) -> None:
        if host_time_ns() >= deadline_ns:
            raise TimeoutError("startup deletion deadline expired")
        info = path.lstat()
        if (
            stat.S_ISLNK(info.st_mode)
            or getattr(info, "st_file_attributes", 0)
            & stat.FILE_ATTRIBUTE_REPARSE_POINT
            or not (stat.S_ISDIR(info.st_mode) or stat.S_ISREG(info.st_mode))
            or path.resolve(strict=True) != path
        ):
            raise StorageError(f"unsafe path blocks session deletion: {path}")

    check(session)
    children = {
        "protocol-data",
        "spikeglx-data",
        ".cephvr.lock",
        ".cephvr-reservation.json",
    }
    if {p.name for p in session.iterdir()} != children:
        raise StorageError("unexpected session root entries block deletion")
    paths: list[Path] = []

    def collect(directory: Path) -> None:
        check(directory)
        for path in directory.iterdir():
            check(path)
            if path.is_dir():
                collect(path)
            paths.append(path)

    for name in ("protocol-data", "spikeglx-data"):
        collect(session / name)
    for path in paths:
        check(session)
        # Recheck ancestors so a substituted junction cannot redirect deletion.
        for parent in reversed(path.relative_to(session).parents):
            check(session / parent)
        check(path)
        if path.is_dir():
            path.rmdir()
        else:
            path.unlink()
