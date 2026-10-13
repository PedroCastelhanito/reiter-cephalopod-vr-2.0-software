"""Source interpretation shared by retained and deferred image preparation."""

from __future__ import annotations

import json
from hashlib import sha256
from typing import TYPE_CHECKING

from cephvr.visual_stimulus.config.models.artifact_models import Interpretation
from cephvr.visual_stimulus.config.models.display_profile import DisplayProfile
from cephvr.visual_stimulus.config.models.program_model import Asset
from cephvr.visual_stimulus.resources.assets import PreparedAsset
from cephvr.visual_stimulus.resources.media import ImagePixels

if TYPE_CHECKING:
    from cephvr.visual_stimulus.resources.image_source import ImageInfo


def image_validation_key(
    asset: Asset,
    source: PreparedAsset,
    *,
    display: DisplayProfile | None,
    output_count: int,
    dependency_asset: Asset | None,
    dependency_source: PreparedAsset | None,
) -> str:
    """Identify validation compatibility within this Setup without retaining pixels."""
    identity = {
        "source": (source.sha256, source.byte_count),
        "interpretation": asset.model_dump(
            mode="json", include={"profile", "color_override"}
        ),
        "geometry": display.geometry.model_dump(mode="json") if display else None,
        "outputs": output_count,
        "dependency": (
            dependency_source.sha256,
            dependency_source.byte_count,
            dependency_asset.model_dump(
                mode="json", include={"profile", "color_override"}
            ),
        )
        if dependency_source is not None and dependency_asset is not None
        else None,
    }
    return sha256(
        json.dumps(
            identity, sort_keys=True, separators=(",", ":"), allow_nan=False
        ).encode("utf-8")
    ).hexdigest()


def image_interpretation(
    asset: Asset, image: ImagePixels | ImageInfo
) -> Interpretation:
    identity = f"{asset.asset_id}-source-v1"
    if len(identity) > 128:
        identity = f"image-source-{sha256(asset.asset_id.encode('utf-8')).hexdigest()}"
    bits = 16 if image.dtype == "uint16" else 8
    override = asset.color_override
    return Interpretation(
        interpretation_id=identity,
        width=image.width,
        height=image.height,
        source_component_bits=tuple(bits for _ in image.channel_order),
        pixel_format=str(image.dtype),
        channel_order=image.channel_order,
        row_origin="top_left",
        source_alpha=image.alpha,
        transfer=image.transfer,
        primaries="rec709_d65",
        range=override.range if override else "full",
        matrix=override.matrix if override else "rgb",
        chroma_location=override.chroma_location if override else "none",
        orientation_degrees=0,
        mirror_x=False,
        sample_aspect_numerator=1,
        sample_aspect_denominator=1,
        resolution_origin="explicit_override" if override else "source_metadata",
        effective_override_reason=override.reason if override else None,
    )
