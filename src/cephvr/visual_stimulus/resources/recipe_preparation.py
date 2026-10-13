"""Prepare protected legacy recipes through the existing image resource contract."""

from typing import Any

import numpy as np

from cephvr.visual_stimulus.config.models.display_profile import DisplayProfile
from cephvr.visual_stimulus.config.models.program_model import Asset
from cephvr.visual_stimulus.resources.budget import PreparationBudget
from cephvr.visual_stimulus.resources.media import ImagePixels
from cephvr.visual_stimulus.resources.texture_recipe import (
    TextureRecipe,
    estimated_working_bytes,
    generate_texture_recipe,
)


def prepare_recipe_image(
    asset: Asset,
    recipe: TextureRecipe,
    budget: PreparationBudget,
    *,
    owner: str,
    output_count: int,
    display: DisplayProfile | None,
    image_pixels: np.ndarray[Any, Any] | None = None,
) -> ImagePixels:
    """Reserve generation workspace before rasterizing; retain legacy sample values."""
    if asset.color_override is not None and (
        asset.color_override.range != "full"
        or asset.color_override.matrix != "rgb"
        or asset.color_override.chroma_location != "none"
    ):
        raise ValueError(
            "texture recipes produce full-range RGB samples without chroma subsampling"
        )
    size = recipe.resolution
    pixel_count = size * size
    working_bytes = estimated_working_bytes(recipe)
    if recipe.pattern == "image" and image_pixels is not None:
        pixel_count = int(image_pixels.shape[0]) * int(image_pixels.shape[1])
        working_bytes = pixel_count * 64
    budget.check_cancelled_or_expired()
    budget.reserve(
        owner=owner,
        cpu_bytes=max(working_bytes, pixel_count * 64),
        gpu_bytes=pixel_count * 16 * output_count,
    )
    corners: dict[str, object] | None = None
    if display is not None:
        corners = {
            surface.surface_id: (
                surface.bottom_left_mm,
                surface.bottom_right_mm,
                surface.top_right_mm,
                surface.top_left_mm,
            )
            for surface in display.geometry.surfaces
        }
    pixels = generate_texture_recipe(
        recipe,
        surface_corners=corners,
        image_pixels=image_pixels,
        check=budget.check_cancelled_or_expired,
    )
    budget.check_cancelled_or_expired()
    return ImagePixels(
        int(pixels.shape[1]),
        int(pixels.shape[0]),
        str(pixels.dtype),
        3,
        ("red", "green", "blue"),
        pixels,
        asset.color_override.transfer if asset.color_override else "linear",
        "none",
    )
