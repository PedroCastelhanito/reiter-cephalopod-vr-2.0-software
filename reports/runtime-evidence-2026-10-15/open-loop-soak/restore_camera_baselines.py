"""Restore exact configured-camera snapshots only after proven managed exit."""

import argparse
import hashlib
import json
from pathlib import Path
import time

from pypylon import genicam, pylon

from cephvr.launcher.replacement import _existing_endpoint
from cephvr.shared.credentials import default_runtime_root

OUT = Path(__file__).resolve().parent
parser = argparse.ArgumentParser()
parser.add_argument("--exited-generation", required=True)
args = parser.parse_args()
receipt_path = default_runtime_root() / "recovery" / f"application-exit-{args.exited_generation}.json"
receipt = json.loads(receipt_path.read_text())
assert receipt["controller_generation"] == args.exited_generation
assert receipt["all_owned_processes_absent"]
endpoint = _existing_endpoint(default_runtime_root())
assert endpoint is None or endpoint.controller_generation == args.exited_generation
assert json.loads((OUT / "user-stop-processes.json").read_text(encoding="utf-8-sig")) == []
record = dict(scope="Restore original full preflight PFS after managed ownership release", receipt=receipt, cameras=[])
factory = pylon.TlFactory.GetInstance()
devices = {device.GetSerialNumber(): device for device in factory.EnumerateDevices()}
serials = ("40065509", "40747103", "40278236")
baselines = {serial: (OUT / f"{serial}-baseline.pfs").read_text() for serial in serials}
assert all(serial in devices for serial in serials)
for serial in serials:
    row = dict(serial=serial, begin_ns=time.perf_counter_ns())
    record["cameras"].append(row)
    camera = None
    try:
        original = baselines[serial]
        camera = pylon.InstantCamera(factory.CreateDevice(devices[serial]))
        camera.Open()
        node_map = camera.GetNodeMap()
        # Existing ROI offsets can prevent the original larger dimensions loading.
        for name in ("OffsetX", "OffsetY"):
            node = node_map.GetNode(name)
            if node is not None and genicam.IsWritable(node):
                node.SetValue(node.GetMin())
        pylon.FeaturePersistence.LoadFromString(original, node_map, True)
        actual = pylon.FeaturePersistence.SaveToString(node_map)
        (OUT / f"{serial}-restored.pfs").write_text(actual)
        row.update(original_sha256=hashlib.sha256(original.encode()).hexdigest(),
                   actual_sha256=hashlib.sha256(actual.encode()).hexdigest(),
                   exact_persistent_text_match=actual == original)
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
        (OUT / "camera-restoration.json").write_text(json.dumps(record, indent=2))
print(json.dumps(record, indent=2))
if any(row.get("error") or not row.get("closed") or not row.get("exact_persistent_text_match") for row in record["cameras"]):
    raise SystemExit(1)
