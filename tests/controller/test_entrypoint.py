"""The supervisor's module launch must enter the controller CLI."""

from __future__ import annotations

import subprocess
import sys


def test_controller_module_enters_cli_without_starting_devices() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "cephvr.controller.main", "--help"],
        check=False,
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert result.returncode == 0, result.stderr
    assert "--bootstrap-handle" in result.stdout
    assert "CephVR controller supervised process" in result.stdout
