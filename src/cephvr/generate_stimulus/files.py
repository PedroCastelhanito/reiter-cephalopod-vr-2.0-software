"""Bounded authoring inputs and atomic publication, without runtime ownership."""

import json
import os
import tempfile
from pathlib import Path
from typing import Any

from cephvr.visual_stimulus.configuration import load_file_policies


def limits() -> Any:
    return load_file_policies(Path(__file__).resolve().parents[3]).limits


def read_bytes(path: Path, maximum: int) -> bytes:
    with path.open("rb") as source:
        data = source.read(maximum + 1)
    if len(data) > maximum:
        raise ValueError(f"File exceeds preparation budget: {path.name}")
    return data


def dependency(root: Path, name: str) -> Path:
    path = (root / name).resolve()
    if not path.is_relative_to(root.resolve()):
        raise ValueError("Dependencies must remain within the selected asset root")
    return path


def json_bytes(value: Any) -> bytes:
    return (json.dumps(value, indent=2, allow_nan=False) + "\n").encode("utf-8")


def atomic_write(path: Path, data: bytes) -> None:
    """Replace only after a complete sibling temporary file has been flushed."""
    fd, name = tempfile.mkstemp(prefix=".cephvr-", dir=path.parent)
    temporary = Path(name)
    try:
        with os.fdopen(fd, "wb") as output:
            output.write(data)
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)
