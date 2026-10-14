"""Bounded fingerprinted calibration input reads for controller admission (V01)."""

import hashlib
from pathlib import Path, PurePosixPath


def read_reference(
    root_value: str, reference: str, expected_sha256: str, maximum: int
) -> tuple[bytes, Path]:
    relative = PurePosixPath(reference)
    if (
        not reference
        or "\\" in reference
        or relative.is_absolute()
        or any(part in ("", ".", "..") for part in relative.parts)
    ):
        raise ValueError("calibration references must be portable relative paths")
    root = Path(root_value).resolve(strict=True)
    path = root.joinpath(*relative.parts).resolve(strict=True)
    if not path.is_relative_to(root) or not path.is_file():
        raise ValueError("calibration reference escapes the accepted asset root")
    before = path.stat()
    if before.st_size > maximum:
        raise ValueError("calibration asset exceeds its accepted byte limit")
    with path.open("rb") as source:
        data = source.read(maximum + 1)
    after = path.stat()
    if (
        len(data) > maximum
        or (before.st_size, before.st_mtime_ns, before.st_ino)
        != (after.st_size, after.st_mtime_ns, after.st_ino)
        or len(data) != after.st_size
    ):
        raise OSError("calibration asset changed while being verified")
    digest = hashlib.sha256(data).hexdigest()
    if len(expected_sha256) != 64 or digest != expected_sha256.lower():
        raise ValueError("calibration asset digest differs from the submitted identity")
    return data, path
