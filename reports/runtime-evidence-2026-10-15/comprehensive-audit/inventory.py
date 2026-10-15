"""Fresh device enumeration and byte-preserved operator settings; no device writes."""

from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys

from pypylon import pylon
from serial.tools import list_ports

from cephvr.gui.calibration_profile import active_monitor_bindings

root = Path.cwd()
out = Path(__file__).parent
record = {
    "revision": subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(),
    "python": sys.version,
    "disk": shutil.disk_usage(root)._asdict(),
    "cameras": [
        {"serial": d.GetSerialNumber(), "model": d.GetModelName()}
        for d in pylon.TlFactory.GetInstance().EnumerateDevices()
    ],
    "ports": [{"device": p.device, "description": p.description} for p in list_ports.comports()],
    "displays": [asdict(m) for m in active_monitor_bindings()],
    "files": {},
}
backup = out / "original-settings"
backup.mkdir(exist_ok=True)
paths = [root / "config" / name for name in ("last_configuration.json", "runtime_gui.json")]
paths += sorted((root / "config" / "backends").glob("*.toml"))
for path in paths:
    if path.exists():
        content = path.read_bytes()
        target = backup / path.name
        if target.exists() and target.read_bytes() != content:
            raise RuntimeError(f"Refusing baseline overwrite: {target}")
        target.write_bytes(content)
        record["files"][str(path.relative_to(root))] = {
            "sha256": hashlib.sha256(content).hexdigest(), "bytes": len(content)
        }
for tool, args in {"nvidia-smi": ["--query-gpu=index,name,uuid,driver_version", "--format=csv"], "ffmpeg": ["-version"]}.items():
    result = subprocess.run([tool, *args], capture_output=True, text=True, timeout=15)
    record[tool] = {"path": shutil.which(tool), "returncode": result.returncode, "stdout": result.stdout, "stderr": result.stderr}
(out / "inventory.json").write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
print(json.dumps(record, indent=2))
