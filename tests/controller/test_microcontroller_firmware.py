"""Execute the Uno sketch with a native Arduino adapter; no board or serial access.

Separate from serial-owner tests because these fixtures compile C++ firmware.
The adapter does not model AVR interrupt latency or electrical timing.
"""

import shutil
import subprocess
from pathlib import Path

import pytest


def test_uno_configuration_preserves_unchanged_pulse_phase(tmp_path: Path) -> None:
    compiler = shutil.which("c++") or shutil.which("g++") or shutil.which("cl")
    if compiler is None:
        pytest.skip("native C++ compiler required for actual-sketch behavior test")
    harness = Path(__file__).with_name("firmware_harness")
    executable = tmp_path / "continuity.exe"
    if Path(compiler).stem.lower() == "cl":
        arguments = [
            "/nologo",
            "/std:c++17",
            "/EHsc",
            f"/I{harness}",
            f"/Fe:{executable}",
        ]
    else:
        arguments = ["-std=c++17", "-I", str(harness), "-o", str(executable)]
    result = subprocess.run(
        [compiler, *arguments, str(harness / "continuity.cpp")],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    subprocess.run([str(executable)], check=True, capture_output=True, timeout=10)
