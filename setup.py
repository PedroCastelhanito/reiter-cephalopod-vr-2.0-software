"""Mark wheels containing native CephVR DLLs as Windows platform wheels."""

from __future__ import annotations

import struct
import sys
import sysconfig
from pathlib import Path

from setuptools import Distribution, setup


def _native_dlls() -> list[Path]:
    return list(Path("src/cephvr").rglob("*.dll"))


def _is_x64_pe(path: Path) -> bool:
    with path.open("rb") as stream:
        if stream.read(2) != b"MZ":
            return False
        stream.seek(0x3C)
        offset_data = stream.read(4)
        if len(offset_data) != 4:
            return False
        stream.seek(struct.unpack("<I", offset_data)[0])
        return stream.read(6) == b"PE\0\0\x64\x86"


class NativeBinaryDistribution(Distribution):
    def has_ext_modules(self) -> bool:
        native_dlls = _native_dlls()
        if native_dlls:
            if (
                sys.platform != "win32"
                or struct.calcsize("P") != 8
                or sysconfig.get_platform() != "win-amd64"
            ):
                raise RuntimeError(
                    "native CephVR DLLs can only be packaged for AMD64 Windows"
                )
            invalid = [path for path in native_dlls if not _is_x64_pe(path)]
            if invalid:
                raise RuntimeError(
                    "native CephVR DLL is not a valid x64 Windows PE image: "
                    + ", ".join(map(str, invalid))
                )
        return bool(native_dlls)


setup(distclass=NativeBinaryDistribution)
