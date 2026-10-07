"""Protected asset acquisition and profile-dispatched preparation inputs."""

from __future__ import annotations

import hashlib
from collections.abc import Callable, Mapping
from contextlib import AbstractContextManager
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import BinaryIO, Protocol

from cephvr.platform.windows.protected_source import ProtectedWindowsSource
from cephvr.visual_stimulus.config.models.artifact_models import ResourceManifest
from cephvr.visual_stimulus.config.models.evidence_model import UniformLayout
from cephvr.visual_stimulus.config.models.program_model import Asset
from cephvr.visual_stimulus.resources.budget import PreparationBudget


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
) -> PreparedAssetSet:
    """Protect and fingerprint every declared asset before any consuming provider opens it.

    `announce(key, path)` must return only after the coordinator has registered the
    exact cleanup obligation. Video sources remain handle-backed; small assets retain
    one immutable byte snapshot to guarantee hash/decode identity.
    """
    if snapshot_limit_bytes <= 0:
        raise ValueError("positive asset snapshot limit is required")
    prepared: list[PreparedAsset] = []
    total_bytes = 0
    seen: set[str] = set()
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
            announce(key, str(path))
            source = source_factory(path)
            try:
                streaming = asset.profile in {
                    "mp4_h264_sdr8_v1",
                    "matroska_ffv1_v3_uint_v1",
                }
                with source.independent_reader() as reader:
                    digest = hashlib.sha256()
                    chunks: list[bytes] = []
                    count = 0
                    while True:
                        budget.check_cancelled_or_expired()
                        request_bytes = (
                            1024 * 1024
                            if streaming
                            else min(1024 * 1024, snapshot_limit_bytes + 1 - count)
                        )
                        if streaming:
                            budget.reserve(
                                owner=f"{owner_prefix}:asset-read-buffer",
                                cpu_bytes=request_bytes,
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
                        if count > snapshot_limit_bytes or streaming:
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
                                    cpu_bytes=1024 * 1024,
                                    gpu_bytes=0,
                                )
                                chunk = reader.read(1024 * 1024)
                                if not chunk:
                                    budget.release(
                                        owner=f"{owner_prefix}:asset-read-buffer"
                                    )
                                    break
                                digest.update(chunk)
                                count += len(chunk)
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
        raise
