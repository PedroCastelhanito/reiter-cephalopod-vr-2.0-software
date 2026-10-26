"""Best-effort native camera title colors; Windows retains chrome/input ownership."""

import ctypes
from ctypes import wintypes

from cephvr.control.v1 import services_pb2 as rpc


def color_preview_caption(handle: int, placement: rpc.PreviewWindowPlacement) -> bool:
    api = ctypes.WinDLL("dwmapi")
    setter = api.DwmSetWindowAttribute
    setter.argtypes = [wintypes.HWND, wintypes.DWORD, ctypes.c_void_p, wintypes.DWORD]
    setter.restype = ctypes.c_long
    applied = True
    for field, attribute in (
        ("camera_caption_rgb", 35),
        ("camera_caption_text_rgb", 36),
    ):
        rgb = getattr(placement, field) if placement.HasField(field) else None
        if rgb is not None and not 0 <= rgb <= 0xFFFFFF:
            raise ValueError("Preview caption color must be packed RGB")
        color = wintypes.DWORD(
            0xFFFFFFFF
            if rgb is None
            else (rgb & 255) << 16 | (rgb & 0xFF00) | rgb >> 16
        )
        # Older Windows versions reject these attributes; keep their native colors.
        applied = (
            setter(handle, attribute, ctypes.byref(color), ctypes.sizeof(color)) >= 0
            and applied
        )
    return applied
