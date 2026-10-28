"""Protected, repeatable image loading for bounded renderer residency."""

from __future__ import annotations

import hashlib
import json
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from functools import lru_cache
from importlib.metadata import PackageNotFoundError, version
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .image_crops import ImageCrop

from cephvr.visual_stimulus.config.media_profiles import TEXTURE_RECIPE_PROFILES
from cephvr.visual_stimulus.config.models.display_profile import DisplayProfile
from cephvr.visual_stimulus.config.models.program_model import Asset
from cephvr.visual_stimulus.resources.assets import PreparedAsset
from cephvr.visual_stimulus.resources.budget import PreparationBudget
from cephvr.visual_stimulus.resources.media import Alpha, ImagePixels, Transfer

from .image_timing import ImageTimings

Check = Callable[[], None]
PixelBuffer = bytes | bytearray | memoryview
LoadPixels = Callable[[Check], PixelBuffer]
_CHUNK_BYTES = 1024 * 1024
_IMAGE_CPU_BYTES_PER_PIXEL = 128
_RECIPE_CPU_BYTES_PER_PIXEL = 192
_TEXTURE_GPU_BYTES_PER_PIXEL = 16


@dataclass(frozen=True, slots=True)
class ImageSource:
    key: str
    width: int
    height: int
    cpu_bytes: int
    gpu_bytes: int
    load: LoadPixels
    output_ids: tuple[str, ...] | None = None
    field_recipe: Any = None
    output_crops: tuple[ImageCrop, ...] = ()
    timings: ImageTimings = field(default_factory=ImageTimings, compare=False)
    finish_validation: Callable[[], None] | None = field(default=None, compare=False)


@dataclass(frozen=True, slots=True)
class ImageInfo:
    width: int
    height: int
    dtype: str
    channel_order: tuple[str, ...]
    transfer: Transfer
    alpha: Alpha
    field_recipe: Any = None


def validate_image_source(
    asset: Asset,
    source: PreparedAsset,
    *,
    budget: PreparationBudget,
    owner: str,
    output_count: int,
    max_document_bytes: int,
    display: DisplayProfile | None = None,
    dependency_asset: Asset | None = None,
    dependency_source: PreparedAsset | None = None,
    cached_info: ImageInfo | None = None,
    defer_validation: bool = False,
    validated: Callable[[ImageInfo], None] | None = None,
) -> tuple[ImageSource, ImageInfo]:
    """Inspect/validate a protected image and return an evictable linear-RGBA loader.

    The source handle stays externally owned. Validation reserves the complete
    decoder/conversion peak before reading; the returned byte string is the
    bottom-up premultiplied float32 RGBA upload format. Deferred inspection must
    complete full validation through load/finish_validation before Ready.
    """
    if not owner or output_count <= 0 or max_document_bytes <= 0:
        raise ValueError("image source owner and positive limits are required")
    if asset.asset_id != source.asset_id or asset.profile != source.profile:
        raise ValueError("image source metadata does not match its protected asset")
    if source.byte_count <= 0:
        raise ValueError("protected image source must contain bytes")
    is_recipe = asset.profile in TEXTURE_RECIPE_PROFILES
    if (dependency_asset is None) != (dependency_source is None):
        raise ValueError("recipe image dependency asset and source must be paired")
    if not is_recipe and dependency_asset is not None:
        raise ValueError("only texture recipe sources may have image dependencies")
    if dependency_asset is not None and dependency_source is not None:
        if (
            dependency_asset.asset_id != dependency_source.asset_id
            or dependency_asset.profile != dependency_source.profile
        ):
            raise ValueError("recipe dependency metadata does not match its source")
        if dependency_source.byte_count <= 0:
            raise ValueError("protected recipe image dependency must contain bytes")

    encoded_bytes = source.byte_count + (
        dependency_source.byte_count if dependency_source is not None else 0
    )
    recipe_pattern = None
    if cached_info is not None and not is_recipe:
        info = cached_info
        budget.check_cancelled_or_expired()
    else:
        temporary_owner = f"{owner}:validation"
        try:
            pixels, recipe_pattern = _load_image_pixels(
                asset,
                source,
                check=budget.check_cancelled_or_expired,
                budget=budget,
                owner=temporary_owner,
                encoded_bytes=encoded_bytes,
                max_document_bytes=max_document_bytes,
                display=display,
                dependency_asset=dependency_asset,
                dependency_source=dependency_source,
                metadata_only=defer_validation,
            )
            info = ImageInfo(
                pixels.width,
                pixels.height,
                pixels.dtype,
                pixels.channel_order,
                pixels.transfer,
                pixels.alpha,
                pixels.field_recipe,
            )
            del pixels
        finally:
            budget.release(owner=temporary_owner)
    parse_bytes = 32 * source.byte_count if is_recipe else 0
    cpu_bytes = (
        2 * encoded_bytes
        + _read_buffer_overhead(encoded_bytes)
        + parse_bytes
        + info.width
        * info.height
        * (_RECIPE_CPU_BYTES_PER_PIXEL if is_recipe else _IMAGE_CPU_BYTES_PER_PIXEL)
    )
    gpu_bytes = info.width * info.height * _TEXTURE_GPU_BYTES_PER_PIXEL * output_count
    key = _content_key(
        asset,
        source,
        dependency_asset=dependency_asset,
        dependency_source=dependency_source,
        display=display,
        recipe_pattern=recipe_pattern,
    )

    validation_done = cached_info is not None or not defer_validation
    timings = ImageTimings()

    def load(check: Check) -> PixelBuffer:
        nonlocal validation_done
        started = time.perf_counter_ns()
        loaded, _ = _load_image_pixels(
            asset,
            source,
            check=check,
            budget=None,
            owner=None,
            encoded_bytes=encoded_bytes,
            max_document_bytes=max_document_bytes,
            display=display,
            dependency_asset=dependency_asset,
            dependency_source=dependency_source,
        )
        if (
            loaded.width,
            loaded.height,
            loaded.dtype,
            loaded.channel_order,
            loaded.transfer,
            loaded.alpha,
        ) != (
            info.width,
            info.height,
            info.dtype,
            info.channel_order,
            info.transfer,
            info.alpha,
        ):
            raise ValueError(
                "decoded interpretation differs from prepared image metadata"
            )
        decoded = time.perf_counter_ns()
        timings.record("source_decode", decoded - started)
        result = _linear_rgba_bytes(loaded)
        timings.record("source_convert", time.perf_counter_ns() - decoded)
        _validate_linear_output(result, info)
        if not validation_done:
            if validated is not None:
                validated(info)
            validation_done = True
        return result

    def finish_validation() -> None:
        if validation_done:
            return
        temporary_owner = f"{owner}:final-validation"
        budget.reserve(owner=temporary_owner, cpu_bytes=cpu_bytes, gpu_bytes=0)
        try:
            load(budget.check_cancelled_or_expired)
        finally:
            budget.release(owner=temporary_owner)

    return ImageSource(
        key,
        info.width,
        info.height,
        cpu_bytes,
        gpu_bytes,
        load,
        field_recipe=info.field_recipe,
        timings=timings,
        finish_validation=finish_validation if defer_validation else None,
    ), info


def read_source_bytes(source: PreparedAsset, check: Check) -> bytes:
    """Read and verify an immutable protected source in bounded chunks."""
    if source.byte_count <= 0:
        raise ValueError("protected source must contain bytes")
    return _read_protected(source, check, max_bytes=None, verify_hash=True)


def _read_protected(
    source: PreparedAsset,
    check: Check,
    *,
    max_bytes: int | None,
    verify_hash: bool,
) -> bytes:
    if max_bytes is not None and source.byte_count > max_bytes:
        raise ValueError("texture recipe exceeds the JSON document limit")
    digest = hashlib.sha256()
    if source.data is not None:
        raw = source.data
        if verify_hash:
            for offset in range(0, len(raw), _CHUNK_BYTES):
                check()
                digest.update(raw[offset : offset + _CHUNK_BYTES])
    else:
        chunks: list[bytes] = []
        count = 0
        with source.source.independent_reader() as reader:
            while True:
                check()
                remaining = source.byte_count - count
                request = min(_CHUNK_BYTES, max(1, remaining + 1))
                block = reader.read(request)
                if not block:
                    break
                chunks.append(block)
                count += len(block)
                if verify_hash:
                    digest.update(block)
                if count > source.byte_count:
                    raise ValueError("protected source length changed after validation")
        raw = b"".join(chunks)
    check()
    if len(raw) != source.byte_count:
        raise ValueError("protected source length changed after validation")
    if verify_hash and digest.hexdigest() != source.sha256:
        raise ValueError("protected source content changed after validation")
    return raw


def _read_buffer_overhead(encoded_bytes: int) -> int:
    """Charge chunk headers, list slots and join scratch without bytearray growth."""
    return 192 * (2 + (encoded_bytes + _CHUNK_BYTES - 1) // _CHUNK_BYTES)


def _load_image_pixels(
    asset: Asset,
    source: PreparedAsset,
    *,
    check: Check,
    budget: PreparationBudget | None,
    owner: str | None,
    encoded_bytes: int,
    max_document_bytes: int,
    display: DisplayProfile | None,
    dependency_asset: Asset | None,
    dependency_source: PreparedAsset | None,
    metadata_only: bool = False,
) -> tuple[ImagePixels, str | None]:
    is_recipe = asset.profile in TEXTURE_RECIPE_PROFILES
    base_bytes = (
        2 * encoded_bytes
        + _read_buffer_overhead(encoded_bytes)
        + (32 * source.byte_count if is_recipe else 0)
    )
    if budget is not None:
        assert owner is not None
        budget.reserve(owner=owner, cpu_bytes=base_bytes, gpu_bytes=0)
    raw = _read_protected(
        source,
        check,
        max_bytes=max_document_bytes if is_recipe else None,
        verify_hash=budget is not None,
    )
    recipe_pattern = None
    if is_recipe:
        pixels, recipe_pattern = _render_recipe(
            asset,
            raw,
            check,
            reserve_pixels=(
                None
                if budget is None
                else lambda width, height: _reserve_peak(
                    budget,
                    owner or "",
                    base_bytes,
                    width,
                    height,
                    _RECIPE_CPU_BYTES_PER_PIXEL,
                )
            ),
            max_document_bytes=max_document_bytes,
            display=display,
            dependency_asset=dependency_asset,
            dependency_source=dependency_source,
            verify_dependency_hash=budget is not None,
        )
    else:
        from cephvr.visual_stimulus.resources.media import decode_image

        pixels = decode_image(
            asset,
            raw,
            metadata_only=metadata_only,
            reserve=(
                None
                if budget is None
                else lambda width, height, _channels, _bits: _reserve_peak(
                    budget, owner or "", base_bytes, width, height
                )
            ),
        )
    check()
    return pixels, recipe_pattern


def _reserve_peak(
    budget: PreparationBudget,
    owner: str,
    base_bytes: int,
    width: int,
    height: int,
    bytes_per_pixel: int = _IMAGE_CPU_BYTES_PER_PIXEL,
) -> None:
    if width <= 0 or height <= 0:
        raise ValueError("decoded image dimensions must be positive")
    budget.reserve(
        owner=owner,
        cpu_bytes=base_bytes + width * height * bytes_per_pixel,
        gpu_bytes=0,
    )


def _render_recipe(
    asset: Asset,
    raw: bytes,
    check: Check,
    *,
    reserve_pixels: Callable[[int, int], None] | None,
    max_document_bytes: int,
    display: DisplayProfile | None,
    dependency_asset: Asset | None,
    dependency_source: PreparedAsset | None,
    verify_dependency_hash: bool,
) -> tuple[ImagePixels, str]:
    from cephvr.visual_stimulus.resources.texture_recipe import (
        generate_texture_recipe,
        parse_texture_recipe,
    )

    if asset.color_override is not None and (
        asset.color_override.range != "full"
        or asset.color_override.matrix != "rgb"
        or asset.color_override.chroma_location != "none"
    ):
        raise ValueError(
            "texture recipes produce full-range RGB samples without chroma subsampling"
        )
    from cephvr.visual_stimulus.resources.grating_recipe import interpreted_recipe

    recipe = interpreted_recipe(
        parse_texture_recipe(raw, max_document_bytes=max_document_bytes), asset.profile
    )
    if recipe.physical_field:
        import numpy as np

        if (
            asset.color_override is not None
            and asset.color_override.transfer != "linear"
        ):
            raise ValueError("Physical texture fields require linear color")
        if reserve_pixels is not None:
            reserve_pixels(1, 1)
        return ImagePixels(
            1,
            1,
            "uint8",
            3,
            ("red", "green", "blue"),
            np.zeros((1, 1, 3), dtype=np.uint8),
            "linear",
            "none",
            recipe,
        ), "physical_field_v1"
    image_pixels = None
    if recipe.pattern == "image":
        if dependency_asset is None or dependency_source is None:
            raise ValueError(
                "image texture recipe requires a protected image dependency"
            )
        dependency_raw = _read_protected(
            dependency_source,
            check,
            max_bytes=None,
            verify_hash=verify_dependency_hash,
        )
        from cephvr.visual_stimulus.resources.recipe_dependencies import (
            decode_recipe_image,
        )

        image_pixels = decode_recipe_image(
            dependency_asset,
            dependency_raw,
            lambda width, height, _channels, _bits: (
                reserve_pixels(width, height) if reserve_pixels is not None else None
            ),
        )
        check()
    elif dependency_asset is not None:
        raise ValueError("non-image texture recipe has an unexpected image dependency")

    if image_pixels is None and reserve_pixels is not None:
        reserve_pixels(recipe.resolution, recipe.resolution)
    surface_corners: Mapping[str, object] | None = None
    if display is not None:
        surface_corners = {
            surface.surface_id: (
                surface.bottom_left_mm,
                surface.bottom_right_mm,
                surface.top_right_mm,
                surface.top_left_mm,
            )
            for surface in display.geometry.surfaces
        }
    check()
    pixels = generate_texture_recipe(
        recipe,
        surface_corners=surface_corners,
        image_pixels=None if image_pixels is None else image_pixels.pixels,
        check=check,
    )
    check()
    result = ImagePixels(
        int(pixels.shape[1]),
        int(pixels.shape[0]),
        str(pixels.dtype),
        3,
        ("red", "green", "blue"),
        pixels,
        asset.color_override.transfer if asset.color_override else "linear",
        "none",
    )
    # Only legacy polar rasters depend on display geometry in the content key.
    pattern = recipe.pattern
    if pattern == "polar_grating" and recipe.params.get("tile_local", False):
        pattern = "polar_tile"
    return result, pattern


def _content_key(
    asset: Asset,
    source: PreparedAsset,
    *,
    dependency_asset: Asset | None,
    dependency_source: PreparedAsset | None,
    display: DisplayProfile | None,
    recipe_pattern: str | None,
) -> str:
    identity: dict[str, Any] = {
        "source_sha256": source.sha256,
        "profile": asset.profile,
        "color_interpretation": (
            None
            if asset.color_override is None
            else {
                "transfer": asset.color_override.transfer,
                "primaries": asset.color_override.primaries,
                "range": asset.color_override.range,
                "matrix": asset.color_override.matrix,
                "chroma_location": asset.color_override.chroma_location,
            }
        ),
        "rgba_conversion": "linear-premultiplied-rgba-f32-v1",
        "raster": "cephvr1-texture-raster-v1" if recipe_pattern is not None else None,
        "dependency_sha256": (
            None if dependency_source is None else dependency_source.sha256
        ),
        "dependency_profile": (
            None if dependency_asset is None else dependency_asset.profile
        ),
        "surface_corners": (
            _surface_key(display) if recipe_pattern == "polar_grating" else None
        ),
        "versions": {
            name: _package_version(name)
            for name in ("numpy", "Pillow", "imagecodecs", "tifffile")
            if recipe_pattern is not None or name != "Pillow"
        },
    }
    encoded = json.dumps(identity, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def _surface_key(display: DisplayProfile | None) -> object:
    if display is None:
        return None
    return {
        surface.surface_id: [
            list(surface.bottom_left_mm),
            list(surface.bottom_right_mm),
            list(surface.top_right_mm),
            list(surface.top_left_mm),
        ]
        for surface in sorted(
            display.geometry.surfaces, key=lambda item: item.surface_id
        )
    }


@lru_cache(maxsize=4)
def _package_version(package: str) -> str:
    try:
        return version(package)
    except PackageNotFoundError:
        return "unavailable"


def _linear_rgba_bytes(pixels: ImagePixels) -> memoryview:
    from cephvr.visual_stimulus.rendering.upload import linear_rgba_bytes

    return linear_rgba_bytes(pixels)


def _validate_linear_output(raw: PixelBuffer, info: ImageInfo) -> None:
    expected = info.width * info.height * _TEXTURE_GPU_BYTES_PER_PIXEL
    if len(raw) != expected:
        raise ValueError("decoded image dimensions differ from its RGBA output")
