"""Restore pre-audit camera/settings bytes after exact application absence."""

import argparse
import hashlib
import json
from pathlib import Path
import time

from pypylon import genicam, pylon

parser = argparse.ArgumentParser()
parser.add_argument("--exit-receipt", type=Path, required=True)
options = parser.parse_args()
receipt = json.loads(options.exit_receipt.read_text())
assert receipt["all_owned_processes_absent"] is True
out = Path(__file__).parent
target = out / "final-restoration.json"
assert not target.exists()
record = {"observed_unix_time": time.time(), "exit_receipt": str(options.exit_receipt), "exit": receipt, "cameras": [], "files": {}}
baseline = json.loads((out / "inventory.json").read_text(encoding="utf-8"))["cameras"]
factory = pylon.TlFactory.GetInstance()
devices = {device.GetSerialNumber(): device for device in factory.EnumerateDevices()}
for original in baseline:
    serial = original["serial"]
    camera = pylon.InstantCamera(factory.CreateDevice(devices[serial]))
    row = {"serial": serial, "readback": {}}
    record["cameras"].append(row)
    try:
        camera.Open()
        content = (out / f"camera-{serial}-baseline.pfs").read_bytes()
        assert hashlib.sha256(content).hexdigest() == original["pfs_sha256"]
        pylon.FeaturePersistence.LoadFromString(content.decode(), camera.GetNodeMap(), True)
        for selector in ("TriggerSelector", "LineSelector"):
            if selector in original["readback"]:
                camera.GetNodeMap().GetNode(selector).FromString(original["readback"][selector])
        for name, expected in original["readback"].items():
            node = camera.GetNodeMap().GetNode(name)
            assert node is not None and genicam.IsReadable(node), name
            row["readback"][name] = node.ToString()
            assert row["readback"][name] == expected, (serial, name, expected, row["readback"][name])
        restored = pylon.FeaturePersistence.SaveToString(camera.GetNodeMap()).encode()
        (out / f"camera-{serial}-restored.pfs").write_bytes(restored)
        row["restored_pfs_sha256"] = hashlib.sha256(restored).hexdigest()
        row["pfs_bytes_match"] = restored == content
        row["all_original_readbacks_match"] = True
        for selector in ("TriggerSelector", "LineSelector"):
            if selector in original["readback"]:
                node = camera.GetNodeMap().GetNode(selector)
                node.FromString(original["readback"][selector])
                assert node.ToString() == original["readback"][selector]
    finally:
        camera.Close()
        row["closed"] = not camera.IsOpen()
        target.write_text(json.dumps(record, indent=2)+"\n")
inventory = json.loads((out / "baseline.json").read_text(encoding="utf-8"))
for relative, original in inventory["operator_files"].items():
    path = Path.cwd() / relative
    baseline_bytes = (out / "original-settings" / path.name).read_bytes()
    assert hashlib.sha256(baseline_bytes).hexdigest() == original["sha256"]
    before = path.read_bytes()
    if before != baseline_bytes:
        (out / (path.name + ".before-final-restore")).write_bytes(before)
        path.write_bytes(baseline_bytes)
    record["files"][relative] = {"before_sha256": hashlib.sha256(before).hexdigest(), "after_sha256": hashlib.sha256(path.read_bytes()).hexdigest(), "original_sha256": original["sha256"], "bytes_match": path.read_bytes() == baseline_bytes}
target.write_text(json.dumps(record, indent=2)+"\n")
assert all(row["bytes_match"] for row in record["files"].values())
assert all(row["pfs_bytes_match"] and row["all_original_readbacks_match"] and row["closed"] for row in record["cameras"])
print(json.dumps(record, indent=2))
