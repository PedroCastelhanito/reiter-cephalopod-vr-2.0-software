"""Resolve image-recipe inputs into declared, protected preparation dependencies."""

from collections.abc import Callable
from hashlib import sha256
from io import BytesIO
from pathlib import Path
from typing import Literal

from cephvr.visual_stimulus.config.models.program_model import Asset, ColorOverride
from cephvr.visual_stimulus.resources.media import ImagePixels
from cephvr.visual_stimulus.resources.texture_recipe import TextureRecipe


def image_dependency(root: Path, asset: Asset, recipe: TextureRecipe) -> Asset | None:
    if recipe.pattern != "image":
        return None
    raw = recipe.params.get("texture_path")
    if not isinstance(raw, str) or not raw.strip():
        raise ValueError("image texture recipe requires texture_path")
    relative = Path(raw)
    if relative.is_absolute() or ".." in relative.parts or "\\" in raw:
        raise ValueError(
            "texture_path must be relative to the recipe inside the asset root"
        )
    base = root.resolve(strict=True)
    candidate = (
        (base / asset.logical_path).parent.joinpath(relative).resolve(strict=True)
    )
    if not candidate.is_relative_to(base):
        raise ValueError("texture image resolves outside its asset root")
    profiles: dict[str, Literal["png_uint_v1", "tiff_uint_v1", "jpeg8_v1"]] = {
        ".png": "png_uint_v1",
        ".tif": "tiff_uint_v1",
        ".tiff": "tiff_uint_v1",
        ".jpg": "jpeg8_v1",
        ".jpeg": "jpeg8_v1",
    }
    profile = profiles.get(candidate.suffix.lower())
    if profile is None:
        raise ValueError("texture_path must name a supported PNG, TIFF or JPEG image")
    override = asset.color_override or ColorOverride(
        reason="CephVR1 texture recipe samples authored RGB values directly",
        transfer="linear",
        primaries="rec709_d65",
        range="full",
        matrix="rgb",
        chroma_location="none",
    )
    return Asset(
        asset_id=f"recipe-image-{sha256(asset.asset_id.encode('utf-8')).hexdigest()}",
        logical_path=candidate.relative_to(base).as_posix(),
        profile=profile,
        color_override=override,
    )


def decode_recipe_image(
    asset: Asset,
    data: bytes,
    reserve: Callable[[int, int, int, int], None],
) -> ImagePixels:
    """Match legacy Pillow RGB conversion using only the protected byte snapshot."""
    import numpy as np
    from PIL import Image

    expected = {"png_uint_v1": "PNG", "tiff_uint_v1": "TIFF", "jpeg8_v1": "JPEG"}
    with Image.open(BytesIO(data)) as source:
        if source.format != expected[asset.profile]:
            raise ValueError("texture image format does not match its declared profile")
        width, height = source.size
        reserve(width, height, 3, 8)
        with source.convert("RGB") as converted:
            pixels = np.asarray(converted, dtype=np.uint8)
    return ImagePixels(
        width,
        height,
        "uint8",
        3,
        ("red", "green", "blue"),
        pixels,
        asset.color_override.transfer if asset.color_override else "linear",
        "none",
    )
