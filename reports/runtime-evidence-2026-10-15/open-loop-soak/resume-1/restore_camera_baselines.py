"""Restore only fresh resume baselines after exact application ownership exit."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import time

from pypylon import genicam, pylon
from cephvr.launcher.replacement import _existing_endpoint
from cephvr.shared.credentials import default_runtime_root

out = Path(__file__).resolve().parent
parser = argparse.ArgumentParser()
parser.add_argument("--exited-generation", required=True)
args = parser.parse_args()
receipt = json.loads((default_runtime_root() / "recovery" / f"application-exit-{args.exited_generation}.json").read_text())
assert receipt["controller_generation"] == args.exited_generation and receipt["all_owned_processes_absent"]
endpoint = _existing_endpoint(default_runtime_root()) if (default_runtime_root() / "launcher.json").exists() else None
assert endpoint is None or endpoint.controller_generation == args.exited_generation
command = ["pwsh", "-NoProfile", "-Command", "ConvertTo-Json -InputObject @(Get-CimInstance Win32_Process | Where-Object { $_.Name -match 'python' -and $_.CommandLine -match 'cephvr\\.|start_runtime_gui' } | Select-Object ProcessId,CreationDate,ExecutablePath,CommandLine) -Depth 3"]
inventory = subprocess.run(command, capture_output=True, text=True, check=True)
processes = json.loads(inventory.stdout)
(out / "camera-restoration-processes.json").write_text(json.dumps(dict(command=command, observed_ns=time.perf_counter_ns(), processes=processes), indent=2))
assert processes == [], "Another runtime may own devices; restoration blocked"
serials = ("40065509", "40747103", "40278236")
baselines = {serial: (out / f"{serial}-baseline.pfs").read_text() for serial in serials}
factory = pylon.TlFactory.GetInstance()
devices = {device.GetSerialNumber(): device for device in factory.EnumerateDevices()}
assert all(serial in devices for serial in serials)
record = dict(scope="Single bounded restoration to fresh resume-1 baselines; historical earlier baseline restoration remains separate", receipt=receipt, cameras=[])
for serial in serials:
    row = dict(serial=serial, begin_ns=time.perf_counter_ns())
    record["cameras"].append(row)
    camera = None
    try:
        original = baselines[serial]
        camera = pylon.InstantCamera(factory.CreateDevice(devices[serial]))
        camera.Open()
        node_map = camera.GetNodeMap()
        for name in ("OffsetX", "OffsetY"):
            node = node_map.GetNode(name)
            if node is not None and genicam.IsWritable(node):
                node.SetValue(node.GetMin())
        pylon.FeaturePersistence.LoadFromString(original, node_map, True)
        actual = pylon.FeaturePersistence.SaveToString(node_map)
        (out / f"{serial}-restored.pfs").write_text(actual)
        row.update(original_sha256=hashlib.sha256(original.encode()).hexdigest(), actual_sha256=hashlib.sha256(actual.encode()).hexdigest(), exact_persistent_text_match=actual == original)
        if actual != original:
            row["differences"] = sorted(set(actual.splitlines()) ^ set(original.splitlines()))
    except Exception as error:
        row["error"] = f"{type(error).__name__}: {error}"
    finally:
        if camera is not None:
            try:
                camera.Close()
                row["closed"] = not camera.IsOpen()
            except Exception as error:
                row["close_error"] = f"{type(error).__name__}: {error}"
        row["end_ns"] = time.perf_counter_ns()
        (out / "camera-restoration.json").write_text(json.dumps(record, indent=2))
print(json.dumps(record, indent=2))
if any(row.get("error") or row.get("close_error") or not row.get("closed") or not row.get("exact_persistent_text_match") for row in record["cameras"]):
    raise SystemExit(1)
