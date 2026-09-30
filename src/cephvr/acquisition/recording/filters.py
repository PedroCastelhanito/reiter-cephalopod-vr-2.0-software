"""Bounded FFmpeg linear filter grammar and static image-layout negotiation."""

from __future__ import annotations

from dataclasses import dataclass

from cephvr.acquisition.recording.filter_syntax import (
    _ALLOWED,
    FilterError,
    _is_rgb,
    _is_yuv,
    _normalize_parameters,
    _offset,
    _parse_node,
    _resolve_box,
    _split,
    _valid_color,
)
from cephvr.acquisition.recording.pixel_formats import PIXEL_FORMAT_LAYOUTS

__all__ = [
    "FilterError",
    "FilterResult",
    "ImageFormat",
    "source_format",
    "validate_filter_chain",
]


@dataclass(frozen=True)
class ImageFormat:
    pixel_format: str
    depth: int
    width: int
    height: int
    chroma_x: int
    chroma_y: int
    color_range: str | None
    matrix: str | None


@dataclass(frozen=True)
class FilterResult:
    image: ImageFormat
    stages: tuple[ImageFormat, ...]
    filters: tuple[str, ...]


_RANGES = {"auto", "full", "pc", "limited", "tv", "mpeg", "jpeg"}
_MATRICES = {"bt709", "fcc", "bt470bg", "smpte170m", "smpte240m", "bt2020"}
_SCALE_FLAGS = {
    "fast_bilinear",
    "bilinear",
    "bicubic",
    "experimental",
    "neighbor",
    "area",
    "bicublin",
    "gauss",
    "sinc",
    "lanczos",
    "spline",
    "print_info",
    "accurate_rnd",
    "full_chroma_int",
    "full_chroma_inp",
    "bitexact",
    "error_diffusion",
}


def validate_filter_chain(
    expression: str,
    *,
    source: ImageFormat,
    target_depth: int,
    accepted_pixel_formats: frozenset[str],
    terminal_pixel_format: str,
    output_range: str | None,
    output_matrix: str | None,
) -> FilterResult:
    """Resolve fixed geometry and precision through the allowed linear filter chain."""
    nodes = _split(expression, ",")
    if not expression or not nodes:
        raise FilterError("video filter chain is empty")
    current = source
    stages: list[ImageFormat] = [current]
    names: list[str] = []
    previous_filter = ""
    for node in nodes:
        name, arguments = _parse_node(node)
        if name not in _ALLOWED:
            raise FilterError(f"unsupported filter {name!r}")
        values = _normalize_parameters(name, arguments)
        if name == "format":
            pixel_format = values["pix_fmts"]
            if (
                "," in pixel_format
                or "|" in pixel_format
                or pixel_format not in accepted_pixel_formats
            ):
                raise FilterError(
                    "format filter needs one installed-build pixel format"
                )
            formatted = _format(
                pixel_format,
                current.width,
                current.height,
                current.color_range,
                current.matrix,
            )
            if formatted.depth < target_depth:
                raise FilterError(
                    "format filter reduces depth below recording_bit_depth"
                )
            if pixel_format != current.pixel_format and previous_filter != "scale":
                raise FilterError(
                    "pixel representation change requires explicit scale converter"
                )
            if _is_rgb(current.pixel_format) and _is_yuv(pixel_format):
                if current.matrix is None or current.color_range is None:
                    raise FilterError(
                        "RGB to YUV conversion needs explicit matrix and range metadata"
                    )
            current = formatted
        elif name == "scale":
            width, height = _resolve_box(values, current.width, current.height)
            if width <= 0 or height <= 0:
                raise FilterError("scale output dimensions must be positive")
            for flag in values.get("flags", "").split("+"):
                if flag and flag not in _SCALE_FLAGS:
                    raise FilterError(f"unsupported scaler flag {flag!r}")
            in_range = values.get("in_range", current.color_range)
            out_range = values.get("out_range", in_range)
            in_matrix = values.get("in_color_matrix", current.matrix)
            out_matrix_stage = values.get("out_color_matrix", in_matrix)
            if (
                in_range
                and in_range not in _RANGES
                or out_range
                and out_range not in _RANGES
            ):
                raise FilterError("scale range must use an explicit FFmpeg range enum")
            if (
                in_matrix
                and in_matrix not in _MATRICES
                or out_matrix_stage
                and out_matrix_stage not in _MATRICES
            ):
                raise FilterError(
                    "scale matrix must use an explicit FFmpeg matrix enum"
                )
            if out_range != in_range and (
                "in_range" not in values or "out_range" not in values
            ):
                raise FilterError(
                    "range conversion needs explicit in_range and out_range"
                )
            matrix_input_required = _is_yuv(current.pixel_format)
            if out_matrix_stage != in_matrix and (
                "out_color_matrix" not in values
                or (matrix_input_required and "in_color_matrix" not in values)
            ):
                raise FilterError(
                    "matrix conversion needs explicit applicable input and output matrices"
                )
            current = ImageFormat(
                current.pixel_format,
                current.depth,
                width,
                height,
                current.chroma_x,
                current.chroma_y,
                out_range,
                out_matrix_stage,
            )
        elif name == "crop":
            width, height = _resolve_box(values, current.width, current.height)
            x = _offset(
                values.get("x", "(iw-ow)/2"),
                current.width,
                current.height,
                width,
                height,
            )
            y = _offset(
                values.get("y", "(ih-oh)/2"),
                current.width,
                current.height,
                width,
                height,
            )
            if (
                width <= 0
                or height <= 0
                or x < 0
                or y < 0
                or x + width > current.width
                or y + height > current.height
            ):
                raise FilterError("crop rectangle falls outside its input")
            if (
                x % current.chroma_x
                or width % current.chroma_x
                or y % current.chroma_y
                or height % current.chroma_y
            ):
                raise FilterError("crop rectangle violates chroma alignment")
            if values.get("exact", "0") not in {"0", "1"} or values.get(
                "keep_aspect", "0"
            ) not in {"0", "1"}:
                raise FilterError("crop exact/keep_aspect parameters require 0 or 1")
            current = ImageFormat(
                current.pixel_format,
                current.depth,
                width,
                height,
                current.chroma_x,
                current.chroma_y,
                current.color_range,
                current.matrix,
            )
        elif name == "pad":
            width, height = _resolve_box(values, current.width, current.height)
            x = _offset(
                values.get("x", "0"), current.width, current.height, width, height
            )
            y = _offset(
                values.get("y", "0"), current.width, current.height, width, height
            )
            if (
                width < current.width
                or height < current.height
                or x < 0
                or y < 0
                or x + current.width > width
                or y + current.height > height
            ):
                raise FilterError("pad geometry does not contain the input image")
            if (
                x % current.chroma_x
                or width % current.chroma_x
                or y % current.chroma_y
                or height % current.chroma_y
            ):
                raise FilterError("pad geometry violates chroma alignment")
            if "color" in values and not _valid_color(values["color"]):
                raise FilterError("pad color is not a valid FFmpeg color literal")
            current = ImageFormat(
                current.pixel_format,
                current.depth,
                width,
                height,
                current.chroma_x,
                current.chroma_y,
                current.color_range,
                current.matrix,
            )
        if current.depth < target_depth:
            raise FilterError("filter intermediate drops below recording_bit_depth")
        names.append(name)
        stages.append(current)
        previous_filter = name
    if current.pixel_format != terminal_pixel_format:
        raise FilterError(
            "terminal filter representation differs from explicit -pix_fmt"
        )
    if current.depth != target_depth:
        raise FilterError("terminal filter depth differs from recording_bit_depth")
    if output_range is not None and _range_name(output_range) != _range_name(
        current.color_range
    ):
        raise FilterError("color_range metadata disagrees with final sample range")
    if output_matrix is not None and output_matrix != current.matrix:
        raise FilterError("colorspace metadata disagrees with final sample matrix")
    if not names or "format" not in names:
        raise FilterError(
            "explicit format filter is required for terminal representation"
        )
    return FilterResult(current, tuple(stages), tuple(names))


def source_format(
    pixel_format: str, width: int, height: int, color_range: str | None = None
) -> ImageFormat:
    return _format(pixel_format, width, height, color_range, None)


def _format(
    pixel_format: str,
    width: int,
    height: int,
    color_range: str | None,
    matrix: str | None,
) -> ImageFormat:
    if width <= 0 or height <= 0:
        raise FilterError("image dimensions must be positive")
    try:
        depth, chroma_x, chroma_y = PIXEL_FORMAT_LAYOUTS[pixel_format]
    except KeyError as exc:
        raise FilterError(f"pixel format layout is unknown: {pixel_format}") from exc
    if width % chroma_x or height % chroma_y:
        raise FilterError("image dimensions violate pixel-format chroma geometry")
    return ImageFormat(
        pixel_format, depth, width, height, chroma_x, chroma_y, color_range, matrix
    )


def _range_name(value: str | None) -> str | None:
    if value in {"pc", "jpeg", "full"}:
        return "full"
    if value in {"tv", "mpeg", "limited"}:
        return "limited"
    return value
