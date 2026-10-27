"""Protected asset acquisition and profile-dispatched preparation inputs."""

from __future__ import annotations

import hashlib
import time
from collections.abc import Callable, Mapping
from contextlib import AbstractContextManager
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import TYPE_CHECKING, BinaryIO, Literal, Protocol

from cephvr.platform.windows.protected_source import (
    ProtectedSourceError,
    ProtectedWindowsSource,
)
from cephvr.visual_stimulus.config.media_profiles import TEXTURE_RECIPE_PROFILES
from cephvr.visual_stimulus.config.models.artifact_models import ResourceManifest
from cephvr.visual_stimulus.config.models.evidence_model import UniformLayout
from cephvr.visual_stimulus.config.models.program_model import Asset
from cephvr.visual_stimulus.resources.budget import PreparationBudget
from cephvr.visual_stimulus.resources.progress import PreparationMetrics

if TYPE_CHECKING:
    from cephvr.visual_stimulus.resources.image_source import ImageSource

RELOADABLE_IMAGE_PROFILES = frozenset(
    (
        "png_uint_v1",
        "tiff_uint_v1",
        "jpeg8_v1",
        "cephvr1_texture_json_v1",
        "cephvr_grating_json_v1",
    )
)


def arena_subresource_id(
    asset_id: str, kind: Literal["texture", "dependency"], index: int
) -> str:
    """Keep generated arena IDs valid and bounded for any authored parent ID."""
    digest = hashlib.sha256(f"{asset_id}\0{kind}\0{index}".encode()).hexdigest()
    return f"arena-{kind}-{digest}"


class ProtectedSource(Protocol):
    def independent_reader(self) -> AbstractContextManager[BinaryIO]: ...

    def close_after_consumers(self) -> None: ...


class AssetCatalogue(Protocol):
    @property
    def assets(self) -> tuple[Asset, ...]: ...


@dataclass(slots=True)
class PreparedAsset:
    asset_id: str
    logical_path: str
    profile: str
    sha256: str
    byte_count: int
    source: ProtectedSource
    data: bytes | None


class ProtectedFingerprintCache:
    """Setup-local fingerprints backed by live, write/delete-excluding handles."""

    def __init__(self, budget: PreparationBudget) -> None:
        self.budget = budget
        self.entries: dict[
            tuple[int, int, int], tuple[ProtectedWindowsSource, str, int]
        ] = {}

    def get(self, source: ProtectedSource) -> tuple[str, int] | None:
        if not isinstance(source, ProtectedWindowsSource):
            return None
        identity = source.identity
        entry = self.entries.get(identity)
        if entry is None:
            return None
        previous, digest, count = entry
        try:
            if previous.identity != identity:
                return None
        except ProtectedSourceError:
            # A released handle no longer proves immutability, even at the same path.
            del self.entries[identity]
            return None
        self.entries[identity] = (source, digest, count)
        return digest, count

    def put(self, source: ProtectedSource, digest: str, count: int) -> None:
        if isinstance(source, ProtectedWindowsSource):
            identity = source.identity
            self.budget.reserve(
                owner="visual_stimulus:source-fingerprints",
                cpu_bytes=1024 * (len(self.entries) + (identity not in self.entries)),
                gpu_bytes=0,
            )
            self.entries[identity] = (source, digest, count)


@dataclass(slots=True)
class PreparedAssetSet:
    assets: tuple[PreparedAsset, ...]
    cpu_bytes: int

    def by_id(self) -> dict[str, PreparedAsset]:
        return {asset.asset_id: asset for asset in self.assets}

    def close(self) -> tuple[str, ...]:
        errors = []
        for asset in reversed(self.assets):
            try:
                asset.source.close_after_consumers()
            except Exception as exc:  # closure receipts must retain failed ownership
                errors.append(f"asset:{asset.asset_id}:{exc}")
        return tuple(errors)


@dataclass(frozen=True, slots=True)
class PreparedResourceBundle:
    """Preparation facts passed into the pure program compiler."""

    asset_set: PreparedAssetSet
    manifest: ResourceManifest
    uniform_layouts: tuple[UniformLayout, ...]
    prepared_content: dict[str, object]
    image_sources: dict[str, ImageSource] = field(default_factory=dict)


def _resolve_asset_path(
    root: Path, logical_path: str, override: Path | None = None
) -> Path:
    if override is not None:
        candidate = Path(override).resolve(strict=True)
        if not candidate.is_file():
            raise ValueError("explicit asset mapping must identify a regular file")
        return candidate
    relative = PurePosixPath(logical_path)
    if relative.is_absolute() or any(
        part in ("", ".", "..") for part in relative.parts
    ):
        raise ValueError("asset path must be portable, relative and traversal-free")
    base = root.resolve(strict=True)
    candidate = base.joinpath(*relative.parts).resolve(strict=True)
    if not candidate.is_relative_to(base):
        raise ValueError("asset resolves outside its configured root")
    if not candidate.is_file():
        raise ValueError("asset path is not a regular file")
    return candidate


def _check_recipe_size(
    profile: str, count: int, max_document_bytes: int | None
) -> None:
    if (
        profile in TEXTURE_RECIPE_PROFILES
        and max_document_bytes is not None
        and count > max_document_bytes
    ):
        raise ValueError("texture recipe exceeds its document byte limit")


def prepare_assets(
    program: AssetCatalogue,
    assets_root: Path,
    budget: PreparationBudget,
    *,
    announce: Callable[[str, str | None], None],
    source_factory: Callable[[Path], ProtectedSource] = ProtectedWindowsSource,
    snapshot_limit_bytes: int,
    owner_prefix: str = "visual_stimulus",
    path_overrides: Mapping[str, Path] | None = None,
    max_document_bytes: int | None = None,
    defer_images: bool = False,
    fingerprints: ProtectedFingerprintCache | None = None,
    metrics: PreparationMetrics | None = None,
) -> PreparedAssetSet:
    """Protect and fingerprint every declared asset before any consuming provider opens it.

    `announce(key, path)` must return only after the coordinator has registered the
    exact cleanup obligation. Video sources remain handle-backed; small assets retain
    one immutable byte snapshot to guarantee hash/decode identity.
    """
    if snapshot_limit_bytes <= 0:
        raise ValueError("positive asset snapshot limit is required")
    if max_document_bytes is not None and max_document_bytes <= 0:
        raise ValueError("positive recipe document limit is required")
    prepared: list[PreparedAsset] = []
    total_bytes = 0
    seen: set[str] = set()
    started = time.perf_counter()
    try:
        for asset in program.assets:
            budget.check_cancelled_or_expired()
            if asset.asset_id in seen:
                raise ValueError(f"duplicate asset ID {asset.asset_id}")
            seen.add(asset.asset_id)
            path = _resolve_asset_path(
                assets_root,
                asset.logical_path,
                None if path_overrides is None else path_overrides.get(asset.asset_id),
            )
            key = f"asset:{asset.asset_id}"
            asset_limit = (
                min(snapshot_limit_bytes, max_document_bytes)
                if asset.profile in TEXTURE_RECIPE_PROFILES
                and max_document_bytes is not None
                else snapshot_limit_bytes
            )
            announce(key, str(path))
            source = source_factory(path)
            try:
                streaming = asset.profile in {
                    "mp4_h264_sdr8_v1",
                    "matroska_ffv1_v3_uint_v1",
                } or (defer_images and asset.profile in RELOADABLE_IMAGE_PROFILES)
                cached = (
                    fingerprints.get(source) if streaming and fingerprints else None
                )
                if cached is not None:
                    digest_hex, count = cached
                    _check_recipe_size(asset.profile, count, max_document_bytes)
                    prepared.append(
                        PreparedAsset(
                            asset.asset_id,
                            asset.logical_path,
                            asset.profile,
                            digest_hex,
                            count,
                            source,
                            None,
                        )
                    )
                    if metrics is not None:
                        metrics.fingerprints_reused += 1
                    continue
                with source.independent_reader() as reader:
                    stream_chunk_bytes = 1024 * 1024
                    deferred_image = (
                        defer_images and asset.profile in RELOADABLE_IMAGE_PROFILES
                    )
                    if deferred_image:
                        # Size comes from the protected handle, never a path stat.
                        reader.seek(0, 2)
                        stream_chunk_bytes = min(
                            stream_chunk_bytes, max(1, reader.tell())
                        )
                        reader.seek(0)
                    stream_buffer_bytes = stream_chunk_bytes * (
                        2 if deferred_image else 1
                    )
                    digest = hashlib.sha256()
                    chunks: list[bytes] = []
                    count = 0
                    while True:
                        budget.check_cancelled_or_expired()
                        request_bytes = (
                            stream_chunk_bytes
                            if streaming
                            else min(1024 * 1024, asset_limit + 1 - count)
                        )
                        if streaming:
                            budget.reserve(
                                owner=f"{owner_prefix}:asset-read-buffer",
                                cpu_bytes=stream_buffer_bytes,
                                gpu_bytes=0,
                            )
                        else:
                            budget.reserve(
                                owner=f"{owner_prefix}:asset-snapshots",
                                cpu_bytes=total_bytes + count + request_bytes,
                                gpu_bytes=0,
                            )
                        chunk = reader.read(request_bytes)
                        if not chunk:
                            if streaming:
                                budget.release(
                                    owner=f"{owner_prefix}:asset-read-buffer"
                                )
                            else:
                                budget.reserve(
                                    owner=f"{owner_prefix}:asset-snapshots",
                                    cpu_bytes=total_bytes + count,
                                    gpu_bytes=0,
                                )
                            break
                        count += len(chunk)
                        _check_recipe_size(asset.profile, count, max_document_bytes)
                        if count > asset_limit or streaming:
                            if not streaming:
                                budget.release(owner=f"{owner_prefix}:asset-snapshots")
                                raise MemoryError(
                                    f"asset {asset.asset_id} exceeds the configured snapshot budget"
                                )
                            # A large stream is retained only through its protected source.
                            chunks.clear()
                            digest.update(chunk)
                            budget.release(owner=f"{owner_prefix}:asset-read-buffer")
                            while True:
                                budget.check_cancelled_or_expired()
                                budget.reserve(
                                    owner=f"{owner_prefix}:asset-read-buffer",
                                    cpu_bytes=stream_buffer_bytes,
                                    gpu_bytes=0,
                                )
                                chunk = reader.read(stream_chunk_bytes)
                                if not chunk:
                                    budget.release(
                                        owner=f"{owner_prefix}:asset-read-buffer"
                                    )
                                    break
                                digest.update(chunk)
                                count += len(chunk)
                                _check_recipe_size(
                                    asset.profile, count, max_document_bytes
                                )
                                budget.release(
                                    owner=f"{owner_prefix}:asset-read-buffer"
                                )
                            break
                        chunks.append(chunk)
                        digest.update(chunk)
                if count <= snapshot_limit_bytes and not streaming:
                    # Joining chunk allocations into the immutable snapshot briefly
                    # owns both representations; include that transient peak.
                    budget.reserve(
                        owner=f"{owner_prefix}:asset-snapshots",
                        cpu_bytes=total_bytes + 2 * count,
                        gpu_bytes=0,
                    )
                    data = b"".join(chunks)
                    chunks.clear()
                    del chunk
                    budget.reserve(
                        owner=f"{owner_prefix}:asset-snapshots",
                        cpu_bytes=total_bytes + count,
                        gpu_bytes=0,
                    )
                else:
                    data = None
                if data is not None and len(data) != count:
                    raise OSError("protected asset snapshot length changed")
                if streaming and fingerprints is not None:
                    fingerprints.put(source, digest.hexdigest(), count)
                if metrics is not None:
                    metrics.sources_hashed += 1
                prepared.append(
                    PreparedAsset(
                        asset.asset_id,
                        asset.logical_path,
                        asset.profile,
                        digest.hexdigest(),
                        count,
                        source,
                        data,
                    )
                )
                total_bytes += len(data) if data is not None else 0
            except BaseException:
                source.close_after_consumers()
                raise
        return PreparedAssetSet(tuple(prepared), total_bytes)
    except BaseException:
        partial = PreparedAssetSet(tuple(prepared), total_bytes)
        partial.close()
        budget.release(owner=f"{owner_prefix}:asset-snapshots")
        budget.release(owner=f"{owner_prefix}:asset-read-buffer")
        raise
    finally:
        if metrics is not None:
            metrics.source_seconds += time.perf_counter() - started
