"""Read-only current inventory/configuration summary; do not open devices."""

import json
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from pypylon import pylon
from serial.tools import list_ports

from cephvr.gui.calibration_profile import active_monitor_bindings
from cephvr.launcher.replacement import _existing_endpoint
from cephvr.shared.credentials import default_runtime_root

ROOT = Path(__file__).resolve().parents[3]
OUT = Path(__file__).parent
record = {"date": datetime.now(ZoneInfo("Asia/Tokyo")).isoformat()}
record["cameras"] = [
    {"serial": d.GetSerialNumber(), "model": d.GetModelName()}
    for d in pylon.TlFactory.GetInstance().EnumerateDevices()
]
record["ports"] = [{"device": p.device, "description": p.description} for p in list_ports.comports()]
record["monitors"] = [asdict(m) for m in active_monitor_bindings()]
try:
    endpoint = _existing_endpoint(default_runtime_root())
    record["runtime_generation"] = endpoint.controller_generation if endpoint else None
except Exception as exc:
    record["runtime_error"] = str(exc)
configuration = json.loads((ROOT / "config/last_configuration.json").read_text(encoding="utf-8"))["configuration"]
for backend in configuration.get("backends", []):
    for role in ("behavioral", "tracking"):
        camera = backend.get("acquisition", {}).get(role, {})
        if "pfs_baseline" in camera.get("device", {}):
            camera["device"]["pfs_baseline"] = "<retained; omitted from summary>"
record["saved_configuration"] = configuration
(OUT / "preflight.json").write_text(json.dumps(record, indent=2), encoding="utf-8")
print(json.dumps(record, indent=2))
