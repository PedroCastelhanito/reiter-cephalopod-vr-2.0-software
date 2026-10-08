"""Small FFmpeg filter syntax parser preserving nested and escaped delimiters."""

from __future__ import annotations

import re

from cephvr.shared.ffmpeg_filter_expressions import (
    ExpressionError,
    evaluate_offset,
    resolve_dimensions,
)


class FilterError(ValueError):
    pass


_ALLOWED: dict[str, tuple[str, ...]] = {
    "format": ("pix_fmts",),
    "scale": (
        "w",
        "width",
        "h",
        "height",
        "flags",
        "in_range",
        "out_range",
        "in_color_matrix",
        "out_color_matrix",
    ),
    "crop": ("w", "out_w", "h", "out_h", "x", "y", "exact", "keep_aspect"),
    "pad": ("w", "width", "h", "height", "x", "y", "color"),
    "hflip": (),
    "vflip": (),
}
_ALIASES = {
    "scale": {"width": "w", "height": "h"},
    "crop": {"out_w": "w", "out_h": "h"},
    "pad": {"width": "w", "height": "h"},
}


def _parse_node(node: str) -> tuple[str, list[tuple[str | None, str]]]:
    name, sep, raw = node.partition("=")
    if not name or not name[0].isalpha():
        raise FilterError(f"invalid filter node {node!r}")
    if not sep:
        return name, []
    chunks = _split(raw, ":")
    params: list[tuple[str | None, str]] = []
    for chunk in chunks:
        key, eq, value = chunk.partition("=")
        params.append(
            (_unescape(key) if eq else None, _unescape(value) if eq else _unescape(key))
        )
    return name, params


def _normalize_parameters(
    name: str, params: list[tuple[str | None, str]]
) -> dict[str, str]:
    aliases = _ALIASES.get(name, {})
    positional = {
        "format": ("pix_fmts",),
        "scale": ("w", "h", "flags"),
        "crop": ("w", "h", "x", "y"),
        "pad": ("w", "h", "x", "y", "color"),
    }.get(name, ())
    output: dict[str, str] = {}
    position = 0
    for key, value in params:
        if key is None:
            if position >= len(positional):
                raise FilterError(f"too many positional arguments for {name}")
            key = positional[position]
            position += 1
        key = aliases.get(key, key)
        if key not in _ALLOWED[name]:
            raise FilterError(f"unsupported {name} parameter {key!r}")
        if key in output:
            raise FilterError(f"duplicate {name} parameter {key!r}")
        if not value:
            raise FilterError(f"empty {name} parameter {key!r}")
        output[key] = value
    if name in {"hflip", "vflip"} and params:
        raise FilterError(f"{name} does not accept parameters")
    return output


def _split(text: str, delimiter: str) -> list[str]:
    parts: list[str] = []
    start = 0
    depth = 0
    quote = ""
    escaped = False
    for index, char in enumerate(text):
        if escaped:
            escaped = False
        elif char == "\\":
            escaped = True
        elif quote:
            if char == quote:
                quote = ""
        elif char in "'\"":
            quote = char
        elif char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
            if depth < 0:
                raise FilterError("unbalanced filter expression parentheses")
        elif char == delimiter and depth == 0:
            parts.append(text[start:index])
            start = index + 1
    if escaped or quote or depth != 0:
        raise FilterError("unterminated escape, quote or parenthesis in filter chain")
    parts.append(text[start:])
    return parts


def _unescape(value: str) -> str:
    output: list[str] = []
    escaped = False
    quote = ""
    for char in value:
        if escaped:
            output.append(char)
            escaped = False
        elif char == "\\":
            escaped = True
        elif quote and char == quote:
            quote = ""
        elif not quote and char in "'\"":
            quote = char
        else:
            output.append(char)
    return "".join(output)


def _resolve_box(values: dict[str, str], iw: int, ih: int) -> tuple[int, int]:
    try:
        return resolve_dimensions(
            values.get("w", "iw"),
            values.get("h", "ih"),
            input_width=iw,
            input_height=ih,
        )
    except ExpressionError as exc:
        raise FilterError(str(exc)) from exc


def _offset(expression: str, iw: int, ih: int, ow: int, oh: int) -> int:
    try:
        return evaluate_offset(expression, iw=iw, ih=ih, ow=ow, oh=oh)
    except ExpressionError as exc:
        raise FilterError(str(exc)) from exc


def _valid_color(value: str) -> bool:
    return bool(
        re.fullmatch(
            r"(?:#[0-9a-fA-F]{6}(?:[0-9a-fA-F]{2})?|0x[0-9a-fA-F]{6}(?:[0-9a-fA-F]{2})?|[a-zA-Z]+)",
            value,
        )
    )


def _is_rgb(pixel_format: str) -> bool:
    return pixel_format.startswith(("rgb", "bgr", "gbr")) or pixel_format == "x2bgr10le"


def _is_yuv(pixel_format: str) -> bool:
    return pixel_format.startswith(("yuv", "yuva")) or pixel_format in {
        "nv12",
        "p010le",
        "p010be",
    }
