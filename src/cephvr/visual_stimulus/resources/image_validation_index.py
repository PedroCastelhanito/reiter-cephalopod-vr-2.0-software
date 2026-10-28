"""Disposable source-folder validation facts, bound to content and decoder versions."""

import hashlib
import json
import logging
import os
import tempfile
from dataclasses import asdict
from functools import lru_cache
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from .image_source import ImageInfo, _package_version
from .media import Alpha, Transfer

INDEX_NAME = ".cephvr-image-validation.json"


class CheckedImage(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    width: int = Field(gt=0, le=1_000_000)
    height: int = Field(gt=0, le=1_000_000)
    dtype: str
    channel_order: tuple[str, ...]
    transfer: Transfer
    alpha: Alpha
    field_recipe: None = None


@lru_cache(maxsize=1)
def validator_identity() -> str:
    from cephvr.visual_stimulus.rendering import upload

    from . import image_interpretation, image_source, media

    digest = hashlib.sha256(b"image-validation-index-v1")
    for module in (upload, image_source, media, image_interpretation):
        assert module.__file__ is not None
        digest.update(Path(module.__file__).read_bytes())
    for name in ("numpy", "Pillow", "imagecodecs", "tifffile"):
        digest.update(f"{name}:{_package_version(name)}".encode())
    return digest.hexdigest()


class ImageValidationIndex:
    def __init__(self, root: Path):
        self.path = root / INDEX_NAME
        self.entries: dict[str, dict[str, Any]] = {}
        self.dirty = False
        try:
            if self.path.stat().st_size > 16 * 1024 * 1024:
                return
            document = json.loads(self.path.read_text(encoding="utf-8"))
            if document.get("validator") == validator_identity() and isinstance(
                document.get("images"), dict
            ):
                self.entries = document["images"]
        except (OSError, ValueError, AttributeError):
            pass

    def get(self, key: str) -> ImageInfo | None:
        try:
            record = self.entries[key]
            parsed = CheckedImage.model_validate_json(json.dumps(record["info"]))
            if parsed.dtype not in ("uint8", "uint16") or parsed.channel_order not in (
                ("red", "green", "blue"),
                ("red", "green", "blue", "alpha"),
                ("gray",),
                ("gray", "alpha"),
            ):
                return None
            return ImageInfo(**parsed.model_dump())
        except (KeyError, TypeError, ValueError):
            return None

    def put(self, key: str, logical_path: str, info: ImageInfo) -> None:
        if info.field_recipe is None:
            self.entries[key] = {"logical_path": logical_path, "info": asdict(info)}
            self.dirty = True

    def save(self) -> None:
        if not self.dirty:
            return
        temporary: str | None = None
        try:
            raw = json.dumps(
                {"validator": validator_identity(), "images": self.entries},
                sort_keys=True,
            )
            if len(raw.encode()) > 16 * 1024 * 1024:
                raise ValueError("image validation index exceeds its size bound")
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=self.path.parent,
                prefix=".cephvr-validation-",
                suffix=".tmp",
                delete=False,
            ) as stream:
                temporary = stream.name
                stream.write(raw)
            os.replace(temporary, self.path)
            temporary = None
            self.dirty = False
        except (OSError, ValueError) as exc:
            logging.getLogger(__name__).warning(
                "Image validation index not saved: %s", exc
            )
        finally:
            if temporary is not None:
                Path(temporary).unlink(missing_ok=True)
