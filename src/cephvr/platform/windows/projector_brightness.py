"""Bounded 32-bit TI SDK invocation; no hardware work at import time."""

import asyncio
import os
import subprocess
import sys
from pathlib import Path


async def adjust_brightness(current_ma: int, timeout_s: float) -> str:
    if not 101 <= current_ma <= 2500:
        raise ValueError("Projector LED current must be between 101 and 2500 mA")
    if sys.platform != "win32":
        raise RuntimeError(
            "Projector brightness requires Windows and the TI DLP EVM SDK"
        )
    if timeout_s <= 0:
        raise TimeoutError("Projector adjustment deadline expired")
    executable = (
        Path(os.environ["WINDIR"]) / "SysWOW64/WindowsPowerShell/v1.0/powershell.exe"
    )
    process = await asyncio.create_subprocess_exec(
        str(executable),
        "-NoProfile",
        "-NonInteractive",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        str(Path(__file__).with_suffix(".ps1")),
        "-Current",
        str(current_ma),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
        creationflags=subprocess.CREATE_NO_WINDOW,
    )
    try:
        output, _ = await asyncio.wait_for(process.communicate(), timeout_s)
    except (TimeoutError, asyncio.CancelledError):
        if process.returncode is None:
            process.kill()
        await process.communicate()
        raise
    details = output.decode(errors="replace").strip()
    if process.returncode:
        raise RuntimeError(details[-6000:] or "TI projector SDK command failed")
    return details[-6000:]
