"""Immutable protected GLB input for a sessionless display diagnostic."""

from __future__ import annotations

import hashlib
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from threading import Event
from typing import TYPE_CHECKING, NoReturn

from cephvr.visual_stimulus.config.models.display_profile import (
    DisplayProfile,
    parse_display_json,
)
from cephvr.visual_stimulus.config.models.program_model import Asset
from cephvr.visual_stimulus.resources.arena import (
    ArenaPreparation,
    AssetInputs,
    prepare_arena,
)
from cephvr.visual_stimulus.resources.assets import (
    PreparedAssetSet,
    ProtectedSource,
    prepare_assets,
)
from cephvr.visual_stimulus.resources.budget import (
    BoundedBudget,
    PreparationBudget,
)
from cephvr.visual_stimulus.resources.calibration import (
    PreparedCalibration,
    prepare_calibration,
)

if TYPE_CHECKING:
    from cephvr.visual_stimulus.rendering.types import OutputActivity
    from cephvr.visual_stimulus.v1.messages_pb2 import OpenDisplayCalibrationCommand


@dataclass(slots=True)
class PreparedDisplayCalibration:
    display: DisplayProfile
    display_calibration: PreparedCalibration
    source: PreparedAssetSet
    arena: ArenaPreparation
    previous_display: DisplayProfile | None = None
    previous_calibration: PreparedCalibration | None = None
    renderer_idle_confirmed: bool = False
    renderer_idle_activities: tuple[OutputActivity, ...] = ()
    resource_keys: tuple[str, ...] = ()
    _closed_source_ids: set[int] = field(default_factory=set, repr=False)

    def close_sources(self) -> bool:
        errors = []
        sources = [item.source for item in self.source.assets]
        sources.extend(item.source for item in self.display_calibration.assets)
        sources.extend(item.source for item in self.arena.sources)
        seen: set[int] = set()
        for source in reversed(sources):
            source_id = id(source)
            if source_id in seen or source_id in self._closed_source_ids:
                continue
            seen.add(source_id)
            try:
                source.close_after_consumers()
                self._closed_source_ids.add(source_id)
            except Exception as exc:
                errors.append(f"protected-source:{source_id}:{exc}")
        return not errors

    @property
    def closed_source_ids(self) -> frozenset[int]:
        return frozenset(self._closed_source_ids)


def prepare_display_calibration(
    display: DisplayProfile,
    display_calibration: PreparedCalibration,
    relative_path: str,
    asset_root: Path,
    expected_size: int,
    expected_sha256: str,
    budget: PreparationBudget,
    *,
    announce: Callable[[str, str | None], None],
    source_factory: Callable[[Path], ProtectedSource],
    maximum_bytes: int,
    output_count: int,
    owner_prefix: str,
    previous_display: DisplayProfile | None = None,
    previous_calibration: PreparedCalibration | None = None,
) -> PreparedDisplayCalibration:
    if expected_size <= 0 or expected_size > maximum_bytes:
        raise ValueError("calibration arena size exceeds the retained asset limit")
    asset = Asset(
        asset_id="display_calibration_arena",
        logical_path=relative_path,
        profile="glb2_static_unlit_v1",
        color_override=None,
    )
    source = prepare_assets(
        AssetInputs((asset,)),
        asset_root,
        budget,
        announce=announce,
        source_factory=source_factory,
        snapshot_limit_bytes=maximum_bytes,
        owner_prefix=owner_prefix,
    )
    prepared = source.assets[0]
    if prepared.byte_count != expected_size or prepared.sha256 != expected_sha256:
        error = ValueError("protected calibration arena size or digest changed")
        _raise_with_cleanup(error, source.close())
    try:
        arena = prepare_arena(
            asset,
            prepared,
            asset_root,
            budget,
            announce=announce,
            source_factory=source_factory,
            max_bytes=maximum_bytes,
            max_elements=max(1, maximum_bytes // 256),
            owner_prefix=owner_prefix,
            output_count=output_count,
        )
        return PreparedDisplayCalibration(
            display,
            display_calibration,
            source,
            arena,
            previous_display,
            previous_calibration,
        )
    except BaseException as error:
        _raise_with_cleanup(error, source.close())


def prepare_display_calibration_request(
    request: OpenDisplayCalibrationCommand,
    announce: Callable[[str, str | None], None],
    deadline_ns: int,
    *,
    check_deadline: Callable[[int], None],
    clock_ns: Callable[[], int],
    cancelled: Event | None,
    source_factory: Callable[[Path], ProtectedSource],
    previous_display: DisplayProfile | None,
    previous_calibration: PreparedCalibration | None,
) -> PreparedDisplayCalibration:
    """Validate one accepted diagnostic request and protect its exact inputs."""
    check_deadline(deadline_ns)
    if not request.HasField("asset_root") or not request.policies.HasField("limits"):
        raise ValueError("calibration requires its accepted asset root and limits")
    limits = request.policies.limits
    for name in (
        "max_document_bytes",
        "max_asset_cpu_bytes",
        "max_asset_gpu_bytes",
    ):
        if not limits.HasField(name) or getattr(limits, name) <= 0:
            raise ValueError(f"calibration requires a positive {name} limit")
    if len(request.profile_json.encode("utf-8")) > limits.max_document_bytes:
        raise ValueError("calibration display profile exceeds its document limit")
    if hashlib.sha256(request.profile_json.encode("utf-8")).hexdigest() != (
        request.profile_sha256
    ):
        raise ValueError("calibration display profile digest changed")
    root = Path(request.asset_root).resolve(strict=True)
    if not root.is_dir():
        raise ValueError("calibration asset root is not a directory")
    display = parse_display_json(
        request.profile_json, max_bytes=limits.max_document_bytes
    )
    budget = BoundedBudget(
        cpu_limit=limits.max_asset_cpu_bytes,
        gpu_limit=limits.max_asset_gpu_bytes,
        cancelled=cancelled,
        deadline_ns=deadline_ns,
        clock_ns=clock_ns,
    )
    owner_prefix = "visual_stimulus:calibration"
    calibration = prepare_calibration(
        display,
        root,
        announce=announce,
        budget=budget,
        max_document_bytes=limits.max_document_bytes,
        owner_prefix=owner_prefix,
        source_factory=source_factory,
    )
    try:
        return prepare_display_calibration(
            display,
            calibration,
            request.arena_relative_path,
            root,
            request.arena_size_bytes,
            request.arena_sha256,
            budget,
            announce=announce,
            source_factory=source_factory,
            maximum_bytes=limits.max_asset_cpu_bytes,
            output_count=max(1, len(display.active_outputs)),
            owner_prefix=owner_prefix,
            previous_display=previous_display,
            previous_calibration=previous_calibration,
        )
    except BaseException as error:
        cleanup_errors = []
        for item in reversed(calibration.assets):
            try:
                item.source.close_after_consumers()
            except Exception as cleanup_error:
                cleanup_errors.append(
                    f"display-calibration:{item.asset_id}:{cleanup_error}"
                )
        if cleanup_errors:
            details = "; ".join(cleanup_errors)
            raise RuntimeError(
                "display calibration preparation failed and protected correction "
                f"sources remain owned: {details}"
            ) from error
        raise


def _raise_with_cleanup(
    error: BaseException, cleanup_errors: tuple[str, ...]
) -> NoReturn:
    if cleanup_errors:
        details = "; ".join(cleanup_errors)
        raise RuntimeError(
            f"display calibration preparation failed and protected inputs remain owned: {details}"
        ) from error
    raise error
