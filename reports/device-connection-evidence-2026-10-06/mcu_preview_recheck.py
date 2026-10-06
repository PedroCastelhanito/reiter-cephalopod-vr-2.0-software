"""Bounded read-only serial protocol probe; no output commands or flashing."""
import json
import time
from datetime import datetime
from pathlib import Path

import serial
from serial.tools import list_ports

result = {"captured_at": datetime.now().astimezone().isoformat(),
          "scope": "COM8 read-only CAPS probe at CephVR2.0 baud; no pulses",
          "ports": [{"port": p.device, "description": p.description}
                    for p in list_ports.comports()]}
try:
    with serial.Serial("COM8", 115200, timeout=0.05, write_timeout=0.2) as port:
        time.sleep(2)
        boot = port.read(port.in_waiting)
        port.write(b"CAPS id=preview-recheck\n")
        deadline = time.monotonic() + 2
        data = bytearray()
        while time.monotonic() < deadline:
            data.extend(port.read(512))
        result.update(boot=boot.decode("ascii", errors="replace"),
                      response=data.decode("ascii", errors="replace"),
                      closed=True)
except Exception as exc:
    result["error"] = f"{type(exc).__name__}: {exc}"
Path(__file__).with_suffix(".json").write_text(json.dumps(result, indent=2))
print(json.dumps(result, indent=2))
