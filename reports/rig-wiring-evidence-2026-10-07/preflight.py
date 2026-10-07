"""Read-only current rig inventory and source provenance; never opens devices."""

import hashlib
import json
import platform
import subprocess
import sys
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from pypylon import pylon
from serial.tools import list_ports

from cephvr.gui.calibration_profile import active_monitor_bindings

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).parent


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


record = {
    "date": datetime.now(ZoneInfo("Asia/Tokyo")).isoformat(),
    "revision": subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
    ).strip(),
    "platform": platform.platform(),
    "python": sys.version,
    "executable": sys.executable,
    "cameras": [
        {"serial": d.GetSerialNumber(), "model": d.GetModelName()}
        for d in pylon.TlFactory.GetInstance().EnumerateDevices()
    ],
    "ports": [
        {"device": p.device, "description": p.description, "hwid": p.hwid}
        for p in list_ports.comports()
    ],
}
try:
    record["monitors"] = [asdict(m) for m in active_monitor_bindings()]
except Exception as exc:
    record["monitor_error"] = str(exc)
try:
    record["nvidia"] = subprocess.check_output(
        ["nvidia-smi", "--query-gpu=name,uuid,pci.bus_id,driver_version", "--format=csv"],
        text=True,
    )
except Exception as exc:
    record["nvidia_error"] = str(exc)
paths = [
    p
    for tree in ("src", "tests", "contracts", "config", "tools", "scripts", "native")
    for p in (ROOT / tree).rglob("*")
    if p.is_file() and "__pycache__" not in p.parts and p.suffix in (
        ".py", ".pyi", ".proto", ".toml", ".json", ".ps1", ".dll", ".pyd", ".i"
    )
]
paths.append(ROOT / "pyproject.toml")
(OUT / "source-sha256.json").write_text(
    json.dumps({p.relative_to(ROOT).as_posix(): digest(p) for p in sorted(paths)}, indent=2),
    encoding="utf-8",
)
(OUT / "preflight.json").write_text(json.dumps(record, indent=2), encoding="utf-8")
print(json.dumps(record, indent=2))
