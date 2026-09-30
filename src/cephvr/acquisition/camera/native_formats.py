"""Explicit Basler EPixelType registry (A01; sdk-mappings.md)."""

from __future__ import annotations

from typing import Any, Literal

from cephvr.shared.pixels.types import NativePixelFormat

_MonoFormat = tuple[
    int, str, Literal["little", "byte"], Literal["lsb", "msb", "packed"]
]
_ColorFormat = tuple[
    int,
    str,
    str,
    Literal["little", "byte"],
    Literal["lsb", "msb", "packed"],
]

_MONO: dict[str, _MonoFormat] = {
    "Mono8": (8, "byte", "little", "lsb"),
    "Mono10": (10, "unpacked", "little", "lsb"),
    "Mono12": (12, "unpacked", "little", "lsb"),
    "Mono16": (16, "unpacked", "little", "lsb"),
    "Mono10packed": (10, "legacy_packed", "little", "packed"),
    "Mono12packed": (12, "legacy_packed", "little", "packed"),
    "Mono10p": (10, "pfnc_packed", "little", "packed"),
    "Mono12p": (12, "pfnc_packed", "little", "packed"),
}
_BAYER: dict[str, _MonoFormat] = {}
for pattern in ("GR", "RG", "GB", "BG"):
    for depth in (8, 10, 12, 16):
        packing = "byte" if depth == 8 else "unpacked"
        byte_order: Literal["byte", "little"] = "byte" if depth == 8 else "little"
        _BAYER[f"Bayer{pattern}{depth}"] = (depth, packing, byte_order, "lsb")
    _BAYER[f"Bayer{pattern}12Packed"] = (12, "legacy_packed", "little", "packed")
    _BAYER[f"Bayer{pattern}10p"] = (10, "pfnc_packed", "little", "packed")
    _BAYER[f"Bayer{pattern}12p"] = (12, "pfnc_packed", "little", "packed")
_COLOR: dict[str, _ColorFormat] = {
    "RGB8packed": (8, "rgb", "byte", "little", "lsb"),
    "BGR8packed": (8, "bgr", "byte", "little", "lsb"),
    "RGB10packed": (10, "rgb", "unpacked", "little", "lsb"),
    "BGR10packed": (10, "bgr", "unpacked", "little", "lsb"),
    "RGB12packed": (12, "rgb", "unpacked", "little", "lsb"),
    "BGR12packed": (12, "bgr", "unpacked", "little", "lsb"),
    "RGB16packed": (16, "rgb", "unpacked", "little", "lsb"),
    "BGR16packed": (16, "bgr", "unpacked", "little", "lsb"),
}

# Exact camera PixelFormat node symbols mapped to pylon EPixelType names. RGB/BGR
# device symbols omit the pylon ``packed`` suffix; keep this distinction explicit.
_DEVICE_TO_PYLON = {
    **{name: name for name in _MONO},
    **{name: name for name in _BAYER},
    "RGB8": "RGB8packed",
    "BGR8": "BGR8packed",
    "RGB10": "RGB10packed",
    "BGR10": "BGR10packed",
    "RGB12": "RGB12packed",
    "BGR12": "BGR12packed",
    "RGB16": "RGB16packed",
    "BGR16": "BGR16packed",
}


def native_pixel_format(pylon: Any, pixel_type: int) -> NativePixelFormat:
    """Resolve a reported numeric EPixelType through exact known enum entries."""
    for name in _device_definitions():
        enum_value = getattr(pylon, f"PixelType_{name}", None)
        if enum_value is None or int(enum_value) != pixel_type:
            continue
        return pylon_pixel_format(name, sdk_value=pixel_type)
    raise ValueError(f"unsupported Basler EPixelType value {pixel_type}")


def device_pixel_format(device_symbol: str, *, sdk_value: int = 0) -> NativePixelFormat:
    """Resolve a confirmed device symbol without importing or loading the SDK."""
    pylon_name = _DEVICE_TO_PYLON.get(device_symbol)
    if pylon_name is None:
        raise ValueError(f"unsupported Basler PixelFormat node value {device_symbol!r}")
    return pylon_pixel_format(pylon_name, sdk_value=sdk_value)


def pylon_pixel_format(pylon_name: str, *, sdk_value: int = 0) -> NativePixelFormat:
    """Resolve a serialized pylon EPixelType name, including RGB/BGR suffixes."""
    try:
        depth, packing, byte_order, alignment = _device_definitions()[pylon_name]
    except KeyError as exc:
        raise ValueError(f"unsupported Basler EPixelType name {pylon_name!r}") from exc
    if pylon_name.startswith("Bayer"):
        channel_layout = "bayer_" + pylon_name[5:7].lower()
    elif pylon_name.startswith(("RGB", "BGR")):
        channel_layout = pylon_name[:3].lower()
    else:
        channel_layout = "mono"
    return NativePixelFormat(
        pylon_name, sdk_value, depth, channel_layout, packing, byte_order, alignment
    )


def _device_definitions() -> dict[str, _MonoFormat]:
    result = dict(_MONO)
    result.update(_BAYER)
    result.update(
        {
            name: (bits, packing, order, align)
            for name, (bits, _, packing, order, align) in _COLOR.items()
        }
    )
    return result


def device_pixel_type(pylon: Any, device_symbol: str) -> int:
    """Resolve an exact camera PixelFormat choice through the separate SDK mapping."""
    pylon_name = _DEVICE_TO_PYLON.get(device_symbol)
    if pylon_name is None:
        raise ValueError(f"unsupported Basler PixelFormat node value {device_symbol!r}")
    pixel_type = getattr(pylon, f"PixelType_{pylon_name}", None)
    if pixel_type is None:
        raise ValueError(f"pypylon does not expose PixelType_{pylon_name}")
    return int(pixel_type)
