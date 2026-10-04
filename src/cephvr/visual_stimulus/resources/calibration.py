"""Protected display-calibration loading for geometric and photometric profiles."""

from __future__ import annotations

import hashlib
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from cephvr.visual_stimulus.config.models.artifact_models import (
    Fingerprint,
    GeometricProfile,
    Resource,
)
from cephvr.visual_stimulus.config.models.display_profile import DisplayProfile
from cephvr.visual_stimulus.config.models.photometric_profile import (
    parse_profile_json,
)
from cephvr.visual_stimulus.config.models.schema_common import parse_json
from cephvr.visual_stimulus.resources.assets import PreparedAsset, ProtectedSource
from cephvr.visual_stimulus.resources.budget import PreparationBudget
from cephvr.visual_stimulus.resources.protected import ProtectedWindowsSource


@dataclass(frozen=True, slots=True)
class PreparedCalibration:
    assets: tuple[PreparedAsset, ...]
    resources: tuple[Resource, ...]
    content: dict[str, object]


def _protected_bytes(
    logical_path: str,
    root: Path,
    *,
    resource_id: str,
    profile_id: str,
    announce: Callable[[str, str | None], None],
    budget: PreparationBudget,
    max_document_bytes: int,
    owner_prefix: str,
    source_factory: Callable[[Path], ProtectedSource],
    path_override: Path | None = None,
) -> tuple[PreparedAsset, bytes]:
    relative = PurePosixPath(logical_path)
    if relative.is_absolute() or any(
        part in ("", ".", "..") for part in relative.parts
    ):
        raise ValueError(
            "calibration path must be portable, relative and traversal-free"
        )
    base = root.resolve(strict=True)
    path = (
        Path(path_override).resolve(strict=True)
        if path_override is not None
        else base.joinpath(*relative.parts).resolve(strict=True)
    )
    if (path_override is None and not path.is_relative_to(base)) or not path.is_file():
        raise ValueError(
            "calibration path must identify a file within the configured asset root"
        )
    key = f"calibration:{resource_id}"
    announce(key, str(path))
    source = source_factory(path)
    try:
        budget.check_cancelled_or_expired()
        budget.reserve(
            owner=f"{owner_prefix}:calibration-read",
            cpu_bytes=max_document_bytes,
            gpu_bytes=0,
        )
        with source.independent_reader() as reader:
            data = reader.read(max_document_bytes + 1)
            if len(data) > max_document_bytes:
                raise MemoryError(
                    f"calibration profile {logical_path} exceeds its document limit"
                )
            if reader.read(1):
                raise OSError("calibration profile changed while being read")
        budget.reserve(
            owner=f"{owner_prefix}:calibration-read", cpu_bytes=len(data), gpu_bytes=0
        )
        asset = PreparedAsset(
            resource_id,
            logical_path,
            profile_id,
            hashlib.sha256(data).hexdigest(),
            len(data),
            source,
            data,
        )
        return asset, data
    except BaseException:
        source.close_after_consumers()
        raise
    finally:
        budget.release(owner=f"{owner_prefix}:calibration-read")


def prepare_calibration(
    display: DisplayProfile,
    assets_root: Path,
    *,
    announce: Callable[[str, str | None], None],
    budget: PreparationBudget,
    max_document_bytes: int,
    owner_prefix: str,
    source_factory: Callable[[Path], ProtectedSource] = ProtectedWindowsSource,
    path_overrides: Mapping[str, Path] | None = None,
) -> PreparedCalibration:
    """Load every referenced mesh/LUT and bind it to the selected physical output."""
    assets: list[PreparedAsset] = []
    resources: list[Resource] = []
    content: dict[str, object] = {}
    try:
        for mapping in display.active_mappings:
            budget.check_cancelled_or_expired()
            resource_id = mapping.mapping_id
            asset, data = _protected_bytes(
                mapping.geometric_profile.logical_path,
                assets_root,
                resource_id=resource_id,
                profile_id="geometric-profile-v1",
                announce=announce,
                budget=budget,
                max_document_bytes=max_document_bytes,
                owner_prefix=owner_prefix,
                source_factory=source_factory,
                path_override=None
                if path_overrides is None
                else path_overrides.get(resource_id),
            )
            assets.append(asset)
            budget.reserve(
                owner=f"{owner_prefix}:calibration:{resource_id}",
                cpu_bytes=len(data) * 64,
                gpu_bytes=0,
            )
            profile = parse_json(
                GeometricProfile,
                data.decode("utf-8"),
                max_bytes=max_document_bytes,
                max_depth=32,
            )
            output = next(
                item
                for item in display.active_outputs
                if item.output_id == mapping.output_id
            )
            if (
                profile.mapping_id != mapping.mapping_id
                or profile.surface_id != mapping.surface_id
                or profile.output_id != output.output_id
                or profile.output_width != output.width_px
                or profile.output_height != output.height_px
                or profile.viewport != mapping.viewport
            ):
                raise ValueError(
                    f"geometric profile {mapping.mapping_id} is incompatible with the display mapping"
                )
            mask_values = len(profile.mask.values) if profile.mask is not None else 0
            weight_values = (
                len(profile.weight.values) if profile.weight is not None else 0
            )
            cpu_bytes = (
                len(data)
                + len(profile.vertices) * 32
                + (mask_values + weight_values) * 8
            )
            gpu_bytes = (
                profile.rows * profile.columns * 16
                + max(0, profile.rows - 1) * max(0, profile.columns - 1) * 24
                + (mask_values + weight_values) * 4
            )
            budget.reserve(
                owner=f"{owner_prefix}:calibration:{resource_id}",
                cpu_bytes=cpu_bytes,
                gpu_bytes=gpu_bytes,
            )
            content[resource_id] = profile
            resources.append(
                Resource(
                    fingerprint=Fingerprint(
                        resource_id=resource_id,
                        logical_path=asset.logical_path,
                        subresource=None,
                        sha256=asset.sha256,
                        bytes=asset.byte_count,
                    ),
                    kind="geometry",
                    profile_id="geometric-profile-v1",
                    dependencies=(),
                    interpretation=None,
                    cpu_bytes=cpu_bytes,
                    gpu_bytes=gpu_bytes,
                    provider_compatibility="cephvr-static-geometric-grid-v1",
                )
            )
        if display.photometric_mode == "calibrated":
            for output in display.active_outputs:
                budget.check_cancelled_or_expired()
                reference = output.photometric_profile
                if reference is None:
                    raise ValueError(
                        f"calibrated output {output.output_id} has no photometric profile"
                    )
                asset, data = _protected_bytes(
                    reference.logical_path,
                    assets_root,
                    resource_id=output.output_id,
                    profile_id="photometric-inverse-lut-v1",
                    announce=announce,
                    budget=budget,
                    max_document_bytes=max_document_bytes,
                    owner_prefix=owner_prefix,
                    source_factory=source_factory,
                )
                assets.append(asset)
                budget.reserve(
                    owner=f"{owner_prefix}:calibration:{output.output_id}",
                    cpu_bytes=len(data) * 64,
                    gpu_bytes=0,
                )
                photometric = parse_profile_json(
                    data.decode("utf-8"), max_bytes=max_document_bytes
                )
                if (
                    photometric.output.output_id != output.output_id
                    or photometric.output.device_identity != output.device_identity
                    or photometric.output.width_px != output.width_px
                    or photometric.output.height_px != output.height_px
                    or photometric.output.rgb_bits != (output.rgb_bits_per_channel,) * 3
                    or photometric.output.refresh_numerator != output.refresh_numerator
                    or photometric.output.refresh_denominator
                    != output.refresh_denominator
                ):
                    raise ValueError(
                        f"photometric profile for {output.output_id} is incompatible with the adopted output"
                    )
                sample_count = (
                    len(photometric.red)
                    + len(photometric.green)
                    + len(photometric.blue)
                )
                cpu_bytes = len(data) + sample_count * 8
                gpu_bytes = sample_count * 4
                budget.reserve(
                    owner=f"{owner_prefix}:calibration:{output.output_id}",
                    cpu_bytes=cpu_bytes,
                    gpu_bytes=gpu_bytes,
                )
                content[output.output_id] = photometric
                resources.append(
                    Resource(
                        fingerprint=Fingerprint(
                            resource_id=output.output_id,
                            logical_path=asset.logical_path,
                            subresource=None,
                            sha256=asset.sha256,
                            bytes=asset.byte_count,
                        ),
                        kind="photometric",
                        profile_id=photometric.profile_id,
                        dependencies=(),
                        interpretation=None,
                        cpu_bytes=cpu_bytes,
                        gpu_bytes=gpu_bytes,
                        provider_compatibility="per-channel-inverse-lut-v1",
                    )
                )
        return PreparedCalibration(tuple(assets), tuple(resources), content)
    except BaseException:
        for asset in reversed(assets):
            try:
                asset.source.close_after_consumers()
            except Exception:
                pass
        for asset in assets:
            budget.release(owner=f"{owner_prefix}:calibration:{asset.asset_id}")
        raise
