"""Source transfer/alpha interpretation and float32 texture upload on an active GL context."""

from collections.abc import Callable
from typing import Any

from cephvr.visual_stimulus.resources.media import ImagePixels


def upload_linear_image(
    context: Any,
    prepared_image: ImagePixels,
    *,
    retain: Callable[[Any], None] | None = None,
    opaque: bool = False,
) -> Any:
    rgba = linear_rgba_bytes(prepared_image, opaque=opaque)
    texture = context.texture(
        (prepared_image.width, prepared_image.height), 4, rgba, dtype="f4"
    )
    if retain is not None:
        retain(texture)
    texture.filter = (0x2601, 0x2601)
    texture.repeat_x = texture.repeat_y = False
    return texture


def linear_rgba_bytes(prepared_image: ImagePixels, *, opaque: bool = False) -> bytes:
    import numpy as np

    pixels = prepared_image.pixels
    maximum = float(np.iinfo(pixels.dtype).max)
    source = pixels.astype(np.float32) / maximum
    if source.ndim == 2:
        source = source[:, :, None]
    if source.shape[2] == 1:
        rgb = np.repeat(source, 3, axis=2)
        alpha = np.ones((*source.shape[:2], 1), dtype=np.float32)
    elif source.shape[2] == 2:
        rgb = np.repeat(source[:, :, :1], 3, axis=2)
        alpha = source[:, :, 1:2]
    else:
        rgb = source[:, :, :3]
        alpha = (
            source[:, :, 3:4]
            if source.shape[2] == 4
            else np.ones((*source.shape[:2], 1), dtype=np.float32)
        )
    if prepared_image.alpha == "none":
        alpha = np.ones((*source.shape[:2], 1), dtype=np.float32)
    if prepared_image.alpha == "associated":
        rgb = np.where(alpha > 0, rgb / np.maximum(alpha, 1e-30), 0)
    if opaque:
        alpha = np.ones((*source.shape[:2], 1), dtype=np.float32)
    if prepared_image.transfer == "srgb":
        rgb = np.where(rgb <= 0.04045, rgb / 12.92, ((rgb + 0.055) / 1.055) ** 2.4)
    elif prepared_image.transfer == "bt709":
        rgb = np.where(rgb < 0.081, rgb / 4.5, ((rgb + 0.099) / 1.099) ** (1 / 0.45))
    rgb *= alpha
    rgba = np.concatenate((rgb, alpha), axis=2).astype(np.float32)
    rgba = np.ascontiguousarray(rgba[::-1])
    return rgba.tobytes()
