"""Persistent per-image Fold bundles in the asset folder's `cephvr-bundles` folder."""

import hashlib
import json
import os
import re
import stat
import uuid
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, BinaryIO

BUNDLE_FOLDER = "cephvr-bundles"
BUNDLE_FORMAT = "cephvr-fold-bundle-v1"
MANIFEST_NAME = "bundle.json"
SAMPLES_NAME = "fold-samples.rgba32f"
_MAX_MANIFEST_BYTES = 1 << 20
_UNSAFE = re.compile(r"[^A-Za-z0-9._-]+")


def _folder_stem(source: str) -> str:
    return _UNSAFE.sub("_", Path(source).stem).lstrip(".")[:64] or "image"


def bundle_key(fields: Mapping[str, Any]) -> str:
    """Digest the canonical key fields; any change selects a different bundle."""
    encoded = json.dumps(fields, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode()).hexdigest()


@dataclass(frozen=True, slots=True)
class StoredBundle:
    directory: Path
    manifest: Mapping[str, Any] | None  # None when unreadable or malformed.

    @property
    def key(self) -> str | None:
        return None if self.manifest is None else self.manifest["key"]

    @property
    def sources(self) -> frozenset[str]:
        return frozenset(() if self.manifest is None else self.manifest["sources"])


def _read_manifest(directory: Path) -> Mapping[str, Any] | None:
    try:
        path = directory / MANIFEST_NAME
        if path.is_symlink() or path.stat().st_size > _MAX_MANIFEST_BYTES:
            return None
        manifest = json.loads(path.read_text(encoding="utf-8"))
        samples = directory / SAMPLES_NAME
        if (
            manifest.get("format") != BUNDLE_FORMAT
            or not isinstance(manifest.get("key"), str)
            or not isinstance(manifest.get("sources"), list)
            or not all(isinstance(name, str) for name in manifest["sources"])
            or not isinstance(manifest.get("byte_count"), int)
            or not isinstance(manifest.get("sha256"), str)
            or samples.is_symlink()
            or samples.stat().st_size != manifest["byte_count"]
        ):
            return None
        return dict(manifest)
    except (OSError, ValueError, AttributeError):
        return None


class BundleStore:
    """Find, publish and (only on request) delete bundles under one asset root."""

    def __init__(self, asset_root: Path) -> None:
        self.root = asset_root.resolve(strict=True) / BUNDLE_FOLDER

    def entries(self) -> tuple[StoredBundle, ...]:
        """Published entries; in-progress and set-aside folders start with a dot."""
        if not self.root.is_dir():
            return ()
        return tuple(
            StoredBundle(path, _read_manifest(path))
            for path in sorted(self.root.iterdir())
            if path.is_dir() and not path.is_symlink() and not path.name.startswith(".")
        )

    @staticmethod
    def stale(
        entries: Iterable[StoredBundle], sources: Iterable[str]
    ) -> tuple[StoredBundle, ...]:
        """Entries for these file names, plus unreadable ones named for them.

        Called only when none matches the current key, so all are replaceable.
        """
        names = frozenset(sources)
        stems = {_folder_stem(name) for name in names}
        return tuple(
            entry
            for entry in entries
            if bool(entry.sources & names)
            or (
                entry.manifest is None
                and entry.directory.name.rsplit(".", 1)[0] in stems
            )
        )

    def begin(self, sources: Iterable[str], key: str) -> "BundleWriter":
        self.root.mkdir(exist_ok=True)
        name = f"{_folder_stem(min(sources))}.{key[:20]}"
        final = self.root / name
        if final.exists():
            # Lookup reads manifests, not names; never move an existing entry.
            final = self.root / f"{name}-{uuid.uuid4().hex[:8]}"
        partial = self.root / f".{name}.partial-{uuid.uuid4().hex}"
        partial.mkdir()
        return BundleWriter(final, partial)

    def delete(self, entry: StoredBundle) -> None:
        """Remove one recorded bundle folder and its known files, never recursively."""
        directory = entry.directory
        if directory.parent != self.root or directory.is_symlink():
            raise ValueError("bundle folder is outside the asset bundle folder")
        unexpected = {p.name for p in directory.iterdir()} - {
            MANIFEST_NAME,
            SAMPLES_NAME,
        }
        if unexpected:
            raise OSError(f"bundle folder holds unexpected files: {sorted(unexpected)}")
        for name in (MANIFEST_NAME, SAMPLES_NAME):  # Manifest first: no valid look.
            path = directory / name
            if path.exists():
                os.chmod(path, stat.S_IREAD | stat.S_IWRITE)
                path.unlink()
        directory.rmdir()


class BundleWriter:
    """Write samples then the manifest into a hidden folder; rename publishes it."""

    def __init__(self, final: Path, partial: Path) -> None:
        self.final = final
        self.partial = partial
        self.file: BinaryIO = (partial / SAMPLES_NAME).open("xb")

    def write(self, pixels: bytes | bytearray | memoryview) -> None:
        if self.file.write(pixels) != len(pixels):
            raise OSError("incomplete Fold bundle write")

    def publish(self, manifest: Mapping[str, Any]) -> Path:
        """Publish with the manifest last; the folder rename makes it visible."""
        self.file.flush()
        os.fsync(self.file.fileno())
        self.file.close()
        path = self.partial / MANIFEST_NAME
        with path.open("x", encoding="utf-8") as file:
            json.dump({**manifest, "format": BUNDLE_FORMAT}, file, sort_keys=True)
            file.flush()
            os.fsync(file.fileno())
        for name in (SAMPLES_NAME, MANIFEST_NAME):
            os.chmod(self.partial / name, stat.S_IREAD)
        self.partial.rename(self.final)
        return self.final

    def abandon(self) -> None:
        """Remove this writer's own unpublished folder after a failed bake."""
        if not self.file.closed:
            self.file.close()
        for path in self.partial.iterdir():
            os.chmod(path, stat.S_IREAD | stat.S_IWRITE)
            path.unlink()
        self.partial.rmdir()
