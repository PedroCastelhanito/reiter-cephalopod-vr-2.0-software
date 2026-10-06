"""Build the typed pypylon Windows-event bridge against the installed pylon SDK."""

from __future__ import annotations

import argparse
import shutil
import struct
import subprocess
import sys
from pathlib import Path

from setuptools import Distribution, Extension


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--sdk", type=Path, default=Path("C:/Program Files/Basler/pylon/Development")
    )
    parser.add_argument("--swig", default=shutil.which("swig"))
    args = parser.parse_args()
    if (
        sys.platform != "win32"
        or struct.calcsize("P") != 8
        or sys.version_info[:2] != (3, 11)
    ):
        parser.error("the bridge requires AMD64 Windows and Python 3.11")
    if not args.swig:
        parser.error("SWIG 4.3.0 is required; install swig==4.3.0")
    version = subprocess.check_output([args.swig, "-version"], text=True)
    if "SWIG Version 4.3.0" not in version:
        parser.error("use SWIG 4.3.0 to match the pinned pypylon type table")
    sdk = args.sdk.resolve()
    if not (sdk / "lib/x64/PylonBase_v11.lib").is_file():
        parser.error("pylon 11 development headers and x64 libraries are required")
    root = Path(__file__).resolve().parents[1]
    output = root / "build/pylon-wait"
    output.mkdir(parents=True, exist_ok=True)
    source = output / "pylon_wait_binding_wrap.cxx"
    subprocess.run(
        [
            args.swig,
            "-c++",
            "-python",
            "-I" + str(root / "native/acquisition"),
            "-outdir",
            str(output),
            "-o",
            str(source),
            str(root / "native/acquisition/pylon_wait_binding.i"),
        ],
        check=True,
    )
    extension = Extension(
        "cephvr.acquisition.camera._pylon_wait_binding",
        [str(source)],
        include_dirs=[str(sdk / "include")],
        library_dirs=[str(sdk / "lib/x64")],
        libraries=["PylonBase_v11"],
        define_macros=[("SWIG_TYPE_TABLE", "pylon")],
        language="c++",
    )
    distribution = Distribution({"ext_modules": [extension]})
    command = distribution.get_command_obj("build_ext")
    command.build_lib = str(root / "src")
    command.build_temp = str(output / "objects")
    command.force = True
    distribution.run_command("build_ext")
    shutil.copy2(
        output / "pylon_wait_binding.py", root / "src/cephvr/acquisition/camera"
    )
    print(
        "Built the typed pylon wait bridge; native wake verification remains required."
    )


if __name__ == "__main__":
    main()
