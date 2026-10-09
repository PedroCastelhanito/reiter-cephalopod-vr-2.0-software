"""Bounded immutable Arduino sketch selection before native compilation (A11)."""

import os
import stat
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path

from cephvr.controller.microcontroller.firmware import FirmwareImage, read_uno_image

MAX_SOURCE_BYTES = 8 * 1024 * 1024
MAX_SOURCE_ENTRIES = 256
_SOURCE_SUFFIXES = frozenset({".ino", ".pde", ".c", ".cpp", ".cxx", ".h", ".hpp", ".s"})


@dataclass(frozen=True)
class FirmwareSketch:
    path: Path
    files: tuple[tuple[Path, bytes], ...]
    digest: str


def read_uno_sketch(path: str, expected_digest: str = "") -> FirmwareSketch:
    """Pin the selected entry point, companion source and recursive src content."""
    source = Path(path)
    if not source.is_absolute() or source.suffix.lower() != ".ino":
        raise ValueError("Select an absolute path to an Arduino .ino sketch.")
    if source.is_symlink():
        raise ValueError(
            f"Firmware sketch must be a regular file, not a link: {source}"
        )
    if not source.exists():
        raise ValueError(
            f"Firmware sketch not found: {source}. Select its current path with Browse."
        )
    if not source.is_file():
        raise ValueError(f"Firmware sketch is not a regular file: {source}")
    root = source.parent
    files: list[tuple[Path, bytes]] = []
    pending = [root]
    entries = 0
    size = 0
    while pending:
        directory = pending.pop()
        with os.scandir(directory) as scan:
            for item in scan:
                entries += 1
                if entries > MAX_SOURCE_ENTRIES:
                    raise ValueError("Firmware sketch exceeds 256 source entries.")
                relative = Path(item.path).relative_to(root)
                if item.name.startswith("."):
                    continue
                attributes = getattr(
                    item.stat(follow_symlinks=False), "st_file_attributes", 0
                )
                if item.is_symlink() or attributes & stat.FILE_ATTRIBUTE_REPARSE_POINT:
                    raise ValueError(
                        f"Firmware source cannot contain links: {relative}"
                    )
                if item.is_dir(follow_symlinks=False):
                    if directory != root or item.name == "src":
                        pending.append(Path(item.path))
                    continue
                if (
                    directory == root
                    and Path(item.name).suffix.lower() not in _SOURCE_SUFFIXES
                ):
                    continue
                if not item.is_file(follow_symlinks=False):
                    raise ValueError(
                        f"Firmware source must be a regular file: {relative}"
                    )
                with Path(item.path).open("rb") as stream:
                    payload = stream.read(MAX_SOURCE_BYTES - size + 1)
                size += len(payload)
                if size > MAX_SOURCE_BYTES:
                    raise ValueError("Firmware sketch exceeds 8 MiB of source.")
                files.append((relative, payload))
    files.sort(key=lambda item: item[0].as_posix())
    if not any(
        relative == Path(source.name) and payload for relative, payload in files
    ):
        raise ValueError("Selected firmware sketch is missing or empty.")
    digest = sha256()
    entry = source.name.encode("utf-8")
    digest.update(len(entry).to_bytes(8, "big"))
    digest.update(entry)
    for relative, payload in files:
        name = relative.as_posix().encode("utf-8")
        digest.update(len(name).to_bytes(8, "big"))
        digest.update(name)
        digest.update(len(payload).to_bytes(8, "big"))
        digest.update(payload)
    pinned = digest.hexdigest()
    if expected_digest and expected_digest != pinned:
        raise ValueError(
            "Firmware source changed after selection; select the sketch again."
        )
    return FirmwareSketch(source, tuple(files), pinned)


def read_firmware(
    path: str, expected_digest: str = ""
) -> FirmwareImage | FirmwareSketch:
    if Path(path).suffix.lower() == ".ino":
        return read_uno_sketch(path, expected_digest)
    return read_uno_image(path, expected_digest)
