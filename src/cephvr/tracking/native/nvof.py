"""Explicit ABI boundary to the small CUDA/Optical Flow SDK owner shim."""

from __future__ import annotations

import ctypes as ct
import sys
from pathlib import Path
from typing import Any

from cephvr.tracking.config.models.methods import FlowSettings
from cephvr.tracking.types import ImageLayout


class NativeFlow:
    def __init__(self) -> None:
        if sys.platform != "win32":
            raise RuntimeError("NVIDIA OF native adapter requires Windows")
        self.dll: Any = ct.CDLL(str(Path(__file__).with_name("cephvr_nvof.dll")))
        signatures = {
            "create": (
                [
                    ct.c_int,
                    ct.c_uint32,
                    ct.c_uint32,
                    ct.c_uint32,
                    ct.c_int,
                    ct.c_int,
                    ct.c_int,
                    ct.c_uint64,
                    ct.POINTER(ct.c_void_p),
                ],
                ct.c_int,
            ),
            "baseline": ([ct.c_void_p, ct.c_void_p], ct.c_int),
            "pair": ([ct.c_void_p, ct.c_void_p], ct.c_int),
            "query": ([ct.c_void_p], ct.c_int),
            "reset": ([ct.c_void_p], ct.c_int),
            "view": (
                [ct.c_void_p, ct.POINTER(ct.c_void_p), ct.POINTER(ct.c_void_p)],
                ct.c_int,
            ),
            "close": ([ct.c_void_p], ct.c_int),
            "error": ([], ct.c_char_p),
        }
        for name, (arguments, result) in signatures.items():
            function = getattr(self.dll, "cephvr_nvof_" + name)
            function.argtypes, function.restype = arguments, result
        self.handle = ct.c_void_p()

    def check(self, code: int) -> int:
        if code < 0:
            raise RuntimeError(self.dll.cephvr_nvof_error().decode("utf8", "replace"))
        return code

    def prepare(
        self, settings: FlowSettings, layout: ImageLayout, maximum: int
    ) -> None:
        self.check(
            self.dll.cephvr_nvof_create(
                settings.device_ordinal,
                layout.width,
                layout.height,
                settings.output_grid_px,
                {"slow": 5, "medium": 10, "fast": 20}[settings.preset],
                settings.output_cost,
                settings.temporal_hints,
                maximum,
                ct.byref(self.handle),
            )
        )

    def upload(self, image: Any, *, baseline: bool) -> None:
        function = (
            self.dll.cephvr_nvof_baseline if baseline else self.dll.cephvr_nvof_pair
        )
        self.check(function(self.handle, ct.c_void_p(image.ctypes.data)))

    def complete(self) -> bool:
        return self.check(self.dll.cephvr_nvof_query(self.handle)) == 1

    def views(self, cells: int) -> tuple[memoryview, memoryview | None]:
        flow, cost = ct.c_void_p(), ct.c_void_p()
        self.check(
            self.dll.cephvr_nvof_view(self.handle, ct.byref(flow), ct.byref(cost))
        )
        if not flow.value:
            raise RuntimeError("missing completed native readback")
        values = (
            memoryview((ct.c_ubyte * (cells * 4)).from_address(flow.value))
            .cast("B")
            .toreadonly()
        )
        quality = (
            None
            if not cost.value
            else memoryview((ct.c_ubyte * cells).from_address(cost.value))
            .cast("B")
            .toreadonly()
        )
        return values, quality

    def reset(self) -> None:
        self.check(self.dll.cephvr_nvof_reset(self.handle))

    def close(self) -> None:
        if self.handle.value:
            self.check(self.dll.cephvr_nvof_close(self.handle))
            self.handle = ct.c_void_p()
