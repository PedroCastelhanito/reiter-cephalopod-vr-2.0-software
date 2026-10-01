"""Profile-checked image/video decoding and source-timestamp indexing.

Optional codec modules load only on use. Unsupported interpretations fail preparation
with an asset-specific diagnostic instead of receiving guessed color or timing.
"""

from __future__ import annotations

import io
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Literal

from cephvr.visual_stimulus.config.models.program_model import Asset

from .image_headers import image_shape

Transfer = Literal["linear", "srgb", "bt709"]
Alpha = Literal["none", "straight", "associated"]


class MediaPreparationError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class ImagePixels:
    width: int
    height: int
    dtype: str
    channel_count: int
    channel_order: tuple[str, ...]
    pixels: Any
    transfer: Transfer
    alpha: Alpha


def _declared_transfer(asset: Asset) -> Literal["linear", "srgb", "bt709", ""]:
    override = asset.color_override
    if override is not None:
        return override.transfer
    return ""


def _png_transfer(data: bytes) -> Literal["linear", "srgb", "bt709", ""]:
    if not data.startswith(b"\x89PNG\r\n\x1a\n"):
        raise MediaPreparationError("PNG signature is invalid")
    offset = 8
    transfer: Literal["linear", "srgb", "bt709", ""] = ""
    while offset + 12 <= len(data):
        length = int.from_bytes(data[offset : offset + 4], "big")
        kind = data[offset + 4 : offset + 8]
        end = offset + 12 + length
        if length > len(data) - offset - 12:
            raise MediaPreparationError("truncated PNG chunk")
        payload = data[offset + 8 : offset + 8 + length]
        if kind == b"iCCP":
            raise MediaPreparationError(
                "embedded ICC profiles require external correction or explicit override"
            )
        if kind == b"sRGB":
            transfer = "srgb"
        elif kind == b"gAMA":
            if length != 4:
                raise MediaPreparationError("invalid PNG gAMA chunk")
            gamma = int.from_bytes(payload, "big")
            if gamma == 100000:
                transfer = "linear"
            elif gamma == 45455:
                transfer = "srgb"
            else:
                raise MediaPreparationError(
                    "PNG gamma is outside supported transfer profiles"
                )
        if kind == b"IEND":
            break
        offset = end
    return transfer


def decode_image(
    asset: Asset,
    data: bytes,
    *,
    reserve: Callable[[int, int, int, int], None] | None = None,
) -> ImagePixels:
    """Decode one supported PNG/TIFF/JPEG image without an RGB8 conversion path."""
    profile = asset.profile
    alpha: Alpha
    if profile == "tiff_uint_v1":
        try:
            import tifffile
        except ImportError as exc:
            raise MediaPreparationError(
                "tifffile and NumPy are required for TIFF assets"
            ) from exc
        with tifffile.TiffFile(io.BytesIO(data)) as source:
            if len(source.pages) != 1 or len(source.series) != 1:
                raise MediaPreparationError(
                    "TIFF profile requires exactly one image and page"
                )
            page = source.pages[0]
            if not isinstance(page, tifffile.TiffPage):
                raise MediaPreparationError("TIFF page is not a decoded image page")
            dtype = page.dtype
            if dtype is None or dtype.kind != "u" or dtype.itemsize not in (1, 2):
                raise MediaPreparationError(
                    "TIFF requires unsigned 8-bit or 16-bit samples"
                )
            if page.photometric not in (
                tifffile.PHOTOMETRIC.MINISBLACK,
                tifffile.PHOTOMETRIC.RGB,
            ):
                raise MediaPreparationError(
                    "TIFF photometric interpretation is unsupported"
                )
            if page.compression not in (
                tifffile.COMPRESSION.NONE,
                tifffile.COMPRESSION.LZW,
                tifffile.COMPRESSION.DEFLATE,
                tifffile.COMPRESSION.ADOBE_DEFLATE,
            ):
                raise MediaPreparationError("TIFF compression is outside its profile")
            if (
                page.tags.get("Orientation") is not None
                and page.tags["Orientation"].value != 1
            ):
                raise MediaPreparationError("unsupported TIFF orientation")
            if reserve is not None:
                reserve(
                    int(page.imagewidth),
                    int(page.imagelength),
                    int(page.samplesperpixel),
                    int(dtype.itemsize) * 8,
                )
            pixels = page.asarray()
            if pixels.ndim == 2:
                channels = 1
            elif pixels.ndim == 3 and pixels.shape[-1] in (2, 3, 4):
                channels = pixels.shape[-1]
            else:
                raise MediaPreparationError("TIFF sample layout is unsupported")
            if channels in (2, 4) and (
                len(page.extrasamples) != 1
                or page.extrasamples[0]
                not in (
                    tifffile.EXTRASAMPLE.UNASSALPHA,
                    tifffile.EXTRASAMPLE.ASSOCALPHA,
                )
            ):
                raise MediaPreparationError("ambiguous TIFF extra sample")
            alpha = (
                "none"
                if channels not in (2, 4)
                else (
                    "associated"
                    if page.extrasamples[0] == tifffile.EXTRASAMPLE.ASSOCALPHA
                    else "straight"
                )
            )
            order = (
                ("gray",)
                if channels == 1
                else ("gray", "alpha")
                if channels == 2
                else tuple(("red", "green", "blue", "alpha")[:channels])
            )
    elif profile in ("png_uint_v1", "jpeg8_v1"):
        try:
            import imagecodecs
        except ImportError as exc:
            raise MediaPreparationError(
                "imagecodecs is required for image assets"
            ) from exc
        shape = image_shape(data, profile)
        if reserve is not None:
            reserve(*shape)
        try:
            pixels = imagecodecs.imread(data)
        except Exception as exc:
            raise MediaPreparationError(
                f"{profile} decoder rejected the asset: {exc}"
            ) from exc
        if pixels.dtype.kind != "u" or pixels.dtype.itemsize not in (1, 2):
            raise MediaPreparationError(
                "image profile requires unsigned 8-bit or 16-bit samples"
            )
        if profile == "jpeg8_v1" and pixels.dtype.itemsize != 1:
            raise MediaPreparationError("JPEG profile requires 8-bit precision")
        if pixels.shape[:2] != (shape[1], shape[0]):
            raise MediaPreparationError(
                "decoded dimensions differ from the source header"
            )
        if pixels.ndim == 2:
            channels = 1
        elif pixels.ndim == 3 and pixels.shape[-1] in (2, 3, 4):
            channels = pixels.shape[-1]
        else:
            raise MediaPreparationError("decoded image channel layout is unsupported")
        if profile == "jpeg8_v1" and channels not in (1, 3):
            raise MediaPreparationError("JPEG profile accepts grayscale or RGB only")
        if channels == 1:
            order = ("gray",)
        elif channels == 2:
            order = ("gray", "alpha")
        else:
            order = tuple(("red", "green", "blue", "alpha")[:channels])
        alpha = "straight" if channels in (2, 4) else "none"
    else:
        raise MediaPreparationError(
            f"asset profile {profile!r} is not a static image profile"
        )
    transfer = _declared_transfer(asset)
    if not transfer and profile == "png_uint_v1":
        transfer = _png_transfer(data)
    if not transfer and profile == "jpeg8_v1":
        # Baseline JPEG without an ICC profile uses the explicit Rec.709 YCbCr
        # interpretation selected by the profile contract; decoder metadata below
        # must still identify RGB output from this decode.
        transfer = "bt709"
    if not transfer:
        raise MediaPreparationError(
            "image transfer/primaries are not explicit; add a supported color override"
        )
    if profile == "jpeg8_v1" and getattr(asset, "color_override", None) is None:
        # JPEG source samples are transformed by the decoder to RGB; its YCbCr
        # range/matrix must not be guessed. Require the override for exact policy.
        raise MediaPreparationError(
            "JPEG color matrix/range require an explicit supported override"
        )
    return ImagePixels(
        int(pixels.shape[1]),
        int(pixels.shape[0]),
        str(pixels.dtype),
        channels,
        tuple(order),
        pixels,
        transfer,
        alpha,
    )
