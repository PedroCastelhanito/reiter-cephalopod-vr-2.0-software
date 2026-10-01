"""Deterministic Setup serialization and at-release atomic recipe publication."""

from __future__ import annotations

import hashlib
import os
import sys
import tempfile
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO

from cephvr.visual_stimulus.compiler import prepared_digest
from cephvr.visual_stimulus.config.models.artifact_models import PreparedTrial
from cephvr.visual_stimulus.config.models.evidence_model import ArtifactRef

RECIPE_SCHEMA_ID = "cephvr.visual_stimulus.prepared_trial.v2"


@dataclass(frozen=True)
class PreparedRecipe:
    """Bytes and identity fixed during Setup; safe to publish at trial release."""

    data: bytes
    sha256: str

    def __post_init__(self) -> None:
        if hashlib.sha256(self.data).hexdigest() != self.sha256:
            raise ValueError("PreparedRecipe digest must be fixed from its Setup bytes")

    @property
    def byte_length(self) -> int:
        return len(self.data)


def prepare_recipe(prepared: PreparedTrial, *, max_bytes: int) -> PreparedRecipe:
    if max_bytes <= 0:
        raise ValueError("prepared recipe byte limit must be positive")
    digest, _, data = prepared_digest(prepared)
    if len(data) > max_bytes:
        raise ValueError(f"prepared recipe is {len(data)} bytes; limit is {max_bytes}")
    return PreparedRecipe(data=data, sha256=digest)


def publish_recipe(
    path: Path,
    relative_path: str,
    recipe: PreparedRecipe,
    *,
    expected_sha256: str,
    expected_byte_length: int,
    trial_start_host_ns: int,
    now_host_ns: int,
    schema_id: str = RECIPE_SCHEMA_ID,
    sync_file: Callable[[BinaryIO], None] | None = None,
) -> ArtifactRef:
    """Publish precomputed recipe bytes exclusively at/after released trial T.

    The temporary file is created beside the reservation, synced, then hard-linked
    into the absent reserved destination so a concurrent writer cannot be replaced.
    The directory entry is synced where the host supports directory fsync.
    """
    if now_host_ns < trial_start_host_ns:
        raise ValueError("recipe cannot be published before released trial onset")
    digest = recipe.sha256
    if (
        digest != expected_sha256
        or len(recipe.data) != expected_byte_length
        or len(recipe.data) != recipe.byte_length
    ):
        raise ValueError("prepared recipe bytes do not match Setup identity")
    path = Path(path)
    if not path.parent.is_dir():
        raise FileNotFoundError(
            f"reserved output directory is not prepared: {path.parent}"
        )
    if path.exists():
        raise FileExistsError(f"reserved stimulus recipe already exists: {path}")
    fd, tmp_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    tmp = Path(tmp_name)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(recipe.data)
            stream.flush()
            if sync_file is not None:
                sync_file(stream)
            elif sys.platform == "win32":
                from cephvr.platform.windows.file_sync import WindowsFrameLogSync

                WindowsFrameLogSync().sync(stream)
            else:
                os.fsync(stream.fileno())
        # Hard-link is atomic and fails rather than replacing an unexpected file.
        os.link(tmp, path)
        tmp.unlink()
        if sys.platform != "win32":
            dir_fd = os.open(path.parent, os.O_RDONLY)
            try:
                os.fsync(dir_fd)
            finally:
                os.close(dir_fd)
    except BaseException:
        try:
            tmp.unlink()
        except FileNotFoundError:
            pass
        raise
    return ArtifactRef(
        relative_path=relative_path,
        sha256=digest,
        byte_length=len(recipe.data),
        schema_id=schema_id,
    )
