"""Owned disposable pixel files; OS deletion on exit and empty-directory recovery."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import BinaryIO, cast
from uuid import uuid4

from .credentials import default_runtime_root


def _lock(file: BinaryIO, acquire: bool) -> None:
    import msvcrt

    file.seek(0)
    msvcrt.locking(file.fileno(), msvcrt.LK_NBLCK if acquire else msvcrt.LK_UNLCK, 1)


def _recover(entry: Path) -> bool:
    record = json.loads(entry.read_text(encoding="utf-8"))
    directory = Path(record["directory"])
    token = entry.stem
    if directory.name != f".cephvr-crops-{token}" or directory.resolve() != directory:
        raise ValueError("temporary bundle path/identity mismatch")
    if not directory.exists():
        entry.unlink()
        return True
    marker = directory / "owner.json"
    if marker.is_symlink():
        raise ValueError("temporary bundle marker is a link")
    with marker.open("r+b") as guard:
        try:
            _lock(guard, True)
        except OSError:
            return False  # A live owner still holds the exact bundle lock.
        try:
            guard.seek(0)
            if json.load(guard) != record:
                raise ValueError("temporary bundle ownership marker mismatch")
            if any(child.name != "owner.json" for child in directory.iterdir()):
                raise OSError(
                    "temporary bundle still contains files; deletion unconfirmed"
                )
        finally:
            _lock(guard, False)
    marker.unlink()
    directory.rmdir()  # Never recursively delete an inferred path.
    entry.unlink()
    return True


def recover_temporary_bundles(root: Path | None = None) -> tuple[str, ...]:
    registry = (root or default_runtime_root()) / "temporary-bundles"
    errors = []
    for entry in registry.glob("*.json"):
        try:
            _recover(entry)
        except (OSError, ValueError, KeyError) as exc:
            errors.append(f"temporary bundle cleanup {entry.name}: {exc}")
    return tuple(errors)


class TemporaryBundle:
    """Per-Setup files; close after all readers, retaining failures for retry."""

    def __init__(self, parent: Path, *, root: Path | None = None) -> None:
        if os.name != "nt":
            raise OSError("temporary pixel bundles require Windows delete-on-close")
        registry = (root or default_runtime_root()) / "temporary-bundles"
        registry.mkdir(parents=True, exist_ok=True)
        token = str(uuid4())
        self.directory = parent.resolve(strict=True) / f".cephvr-crops-{token}"
        self.entry = registry / f"{token}.json"
        self.files: list[BinaryIO] = []
        self.directory.mkdir()
        record = {
            "directory": str(self.directory),
            "format": "cephvr-temporary-bundle-v1",
        }
        self.guard = (self.directory / "owner.json").open("x+b")
        try:
            self.guard.write(json.dumps(record).encode())
            self.guard.flush()
            _lock(self.guard, True)
            self.entry.write_text(json.dumps(record), encoding="utf-8")
        except BaseException:
            self.guard.close()
            (self.directory / "owner.json").unlink()
            self.directory.rmdir()
            self.entry.unlink(missing_ok=True)
            raise

    def add(self, pixels: bytes, *, suffix: str = ".rgba32f") -> BinaryIO:
        file = cast(
            BinaryIO,
            tempfile.NamedTemporaryFile(
                mode="w+b", suffix=suffix, dir=self.directory, delete=True
            ),
        )
        self.files.append(file)
        file.write(pixels)
        file.flush()
        file.seek(0)
        return file

    def close(self) -> None:
        if not self.entry.exists() and not self.directory.exists():
            return
        while self.files:
            self.files[-1].close()
            self.files.pop()
        if not self.guard.closed:
            _lock(self.guard, False)
            self.guard.close()
        _recover(self.entry)
