"""Verify released native ownership after exact shutdown; no board command."""

import json
import subprocess
import tempfile
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import serial

from cephvr.platform.windows.guard import SingleInstanceGuard

out = Path(__file__).parent
receipt = json.loads((out / "final-exit-receipt.json").read_text(encoding="utf-8"))
with SingleInstanceGuard("application"):
    guard_available = True
with serial.Serial("COM8", 115200, timeout=0.1) as port:
    com_exclusive_open = port.is_open
processes = subprocess.check_output(
    ["powershell", "-NoProfile", "-Command", "@(Get-Process -Name cephvr-python,arduino-cli,avr-g++,avrdude -ErrorAction SilentlyContinue | Select-Object Id,ProcessName) | ConvertTo-Json -Compress"],
    text=True,
).strip()
helpers = json.loads(processes) if processes else []
private_dirs = [str(p) for p in Path(tempfile.gettempdir()).glob("cephvr-firmware-*")]
record = {
    "date": datetime.now(ZoneInfo("Asia/Tokyo")).isoformat(),
    "exact_receipt": receipt,
    "application_guard_available_and_released": guard_available,
    "COM8_exclusive_open_and_closed": com_exclusive_open,
    "remaining_owned_runtime_or_tool_processes": helpers,
    "remaining_private_firmware_dirs": private_dirs,
    "scope": "No serial command; opening COM may reset Uno. Board watchdog test already stopped both outputs; no capture/runtime restarted.",
}
(out / "final-native-cleanup.json").write_text(json.dumps(record, indent=2), encoding="utf-8")
assert not helpers and not private_dirs
print("Application guard free, COM8 exclusively opened/closed, zero owned runtime/tool processes or private firmware directories.")
