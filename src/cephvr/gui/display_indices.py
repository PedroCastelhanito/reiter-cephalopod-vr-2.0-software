"""Read active Windows display path numbers; never infer them from Qt screen order."""

import ctypes as ct
import sys


class Luid(ct.Structure):
    _fields_ = [("low", ct.c_uint32), ("high", ct.c_int32)]


class Source(ct.Structure):
    _fields_ = [
        ("adapter", Luid),
        ("id", ct.c_uint32),
        ("mode", ct.c_uint32),
        ("flags", ct.c_uint32),
    ]


class Rational(ct.Structure):
    _fields_ = [("numerator", ct.c_uint32), ("denominator", ct.c_uint32)]


class Target(ct.Structure):
    _fields_ = [
        ("adapter", Luid),
        ("id", ct.c_uint32),
        ("mode", ct.c_uint32),
        ("technology", ct.c_uint32),
        ("rotation", ct.c_uint32),
        ("scaling", ct.c_uint32),
        ("refresh", Rational),
        ("scanline", ct.c_uint32),
        ("available", ct.c_int32),
        ("flags", ct.c_uint32),
    ]


class DisplayPath(ct.Structure):
    _fields_ = [("source", Source), ("target", Target), ("flags", ct.c_uint32)]


class InfoHeader(ct.Structure):
    _fields_ = [
        ("kind", ct.c_uint32),
        ("size", ct.c_uint32),
        ("adapter", Luid),
        ("id", ct.c_uint32),
    ]


class SourceName(ct.Structure):
    _fields_ = [("header", InfoHeader), ("name", ct.c_wchar * 32)]


def windows_display_indices() -> tuple[dict[str, str], str]:
    """Use the active-path numbering used by Microsoft PowerToys PowerDisplay.

    Clone paths share a source and retain all numbers. Native Windows verification
    against Settings is still required on the rig; unknown never becomes a Qt index.
    """
    if sys.platform != "win32":
        return {}, "Windows display indices are unavailable on this operating system."
    try:
        api = ct.WinDLL("user32", use_last_error=True)
        sizes = api.GetDisplayConfigBufferSizes
        sizes.argtypes = [ct.c_uint32, ct.POINTER(ct.c_uint32), ct.POINTER(ct.c_uint32)]
        sizes.restype = ct.c_int32
        query = api.QueryDisplayConfig
        query.argtypes = [
            ct.c_uint32,
            ct.POINTER(ct.c_uint32),
            ct.POINTER(DisplayPath),
            ct.POINTER(ct.c_uint32),
            ct.c_void_p,
            ct.c_void_p,
        ]
        query.restype = ct.c_int32
        info = api.DisplayConfigGetDeviceInfo
        info.argtypes = [ct.POINTER(InfoHeader)]
        info.restype = ct.c_int32
        for _ in range(3):
            paths_count, modes_count = ct.c_uint32(), ct.c_uint32()
            result = sizes(2, ct.byref(paths_count), ct.byref(modes_count))
            if result:
                return {}, f"Windows display enumeration failed ({result})."
            if not paths_count.value:
                return {}, "No active Windows display paths."
            paths = (DisplayPath * paths_count.value)()
            # DISPLAYCONFIG_MODE_INFO is 64 bytes, with an 8-byte-aligned union.
            modes = (ct.c_uint64 * (8 * max(1, modes_count.value)))()
            result = query(
                2, ct.byref(paths_count), paths, ct.byref(modes_count), modes, None
            )
            if result == 122:  # Topology changed between sizing and query.
                continue
            if result:
                return {}, f"Windows display enumeration failed ({result})."
            indices: dict[str, list[str]] = {}
            for index, path in enumerate(paths[: paths_count.value], 1):
                name = SourceName()
                name.header = InfoHeader(
                    1, ct.sizeof(SourceName), path.source.adapter, path.source.id
                )
                if info(ct.byref(name.header)):
                    return {}, "Windows display source identity could not be read."
                indices.setdefault(name.name.casefold(), []).append(str(index))
            return {name: "/".join(values) for name, values in indices.items()}, ""
        return {}, "Display topology changed repeatedly; refresh again."
    except (OSError, AttributeError) as error:
        return {}, f"Windows display indices unavailable: {error}"
