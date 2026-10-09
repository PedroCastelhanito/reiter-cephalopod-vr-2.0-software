"""Bounded real SerialOwner startup probe after normal managed shutdown."""
import json
import time
from pathlib import Path
from google.protobuf.json_format import MessageToDict
from cephvr.controller.microcontroller.config import load_serial_policies
from cephvr.controller.microcontroller.owner import SerialOwner
from cephvr.controller.microcontroller.serial_port import PySerialPort
from cephvr.shared.clock import host_time_ns

root = Path(__file__).resolve().parents[2]
result = {"method": "SerialOwner.connect; COM8/115200, unchanged 100 ms acknowledgement; 10 s diagnostic deadline", "writes": [], "received": [], "read_calls": 0}

class ObservedPort(PySerialPort):
    def write(self, payload):
        start = time.monotonic()
        count = super().write(payload)
        result["writes"].append({"payload": payload.decode("ascii", errors="replace"), "elapsed_s": time.monotonic() - start, "accepted": count})
        return count
    def read(self, size=1):
        result["read_calls"] += 1
        start = time.monotonic()
        data = super().read(size)
        if data:
            result["received"].append({"bytes": data.decode("ascii", errors="replace"), "elapsed_s": time.monotonic() - start})
        return data

start = time.monotonic()
owner = None
try:
    owner = SerialOwner("COM8", load_serial_policies(root), serial_port=ObservedPort("COM8", 115200))
    result["observation"] = MessageToDict(owner.connect(host_time_ns() + 10_000_000_000))
except Exception as exc:
    result["error"] = f"{type(exc).__name__}: {exc}"
finally:
    if owner is not None:
        result["unmatched_replies"] = owner.unmatched_replies
        result["malformed_replies"] = owner.malformed_replies
        try:
            owner.close(host_time_ns() + 5_000_000_000)
            result["closed"] = True
        except Exception as exc:
            result["close_error"] = str(exc)
    result["elapsed_s"] = time.monotonic() - start
    (Path(__file__).parent / "eye-camera-mcu-probe.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: value for key, value in result.items() if key not in {"writes", "received"}}, indent=2))
