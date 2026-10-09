"""Reconcile firmware recovery evidence without replacing earlier camera evidence."""

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import xml.etree.ElementTree as ET

from cephvr.controller.microcontroller.firmware_source import read_firmware

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent


def read(name):
    return json.loads((OUT / name).read_text(encoding="utf-8-sig"))


inputs = read("firmware-picker-inputs.json")
current = {
    path: hashlib.sha256((ROOT / path).read_bytes()).hexdigest()
    for path in inputs["sha256"]
}
drift = [path for path in current if current[path] != inputs["sha256"][path]]
assert drift == ["tests/controller/test_microcontroller_owner.py"], drift
status = read("firmware-picker-verified-status.json")
view = status["microcontroller"]
assert not view.get("failure") and not view.get("cleanup_pending")
observation = view["observation"]
assert observation["port"] == "COM8"
assert observation["capabilities"]["protocol_version"] == 3
assert observation["capabilities"]["firmware"] == "cephvr2_uno_2"
assert all(
    observation["state"][role]["running"] is False
    for role in ("behavioral", "tracking")
)
assert all(
    item.get("complete") and item.get("succeeded")
    for item in status["operations"][1:]
)
checks = {
    name: read(f"firmware-picker-{name}.result.json")
    for name in ("tests", "ruff", "format", "mypy", "boundaries", "dependencies")
}
assert all(item["returncode"] == 0 for item in checks.values())
declarations = read("firmware-picker-declarations.json")
assert not declarations["issues"]
previous_inputs = read("eye-camera-inputs.json")["sha256"]
contract_drift = [
    path for path in current
    if path.startswith(("contracts/", "src/cephvr/tracking/", "src/cephvr/visual_stimulus/"))
    and current[path] != previous_inputs.get(path)
]
assert not contract_drift, contract_drift
contract_checks = {
    name: read(f"eye-camera-{name}.result.json")
    for name in ("tracking-contracts", "visual-contracts", "tracking-schema", "visual-schema")
}
assert all(item["returncode"] == 0 for item in contract_checks.values())
suite = ET.parse(OUT / "firmware-picker-tests.xml").getroot().find("testsuite")
focused = ET.parse(OUT / "firmware-picker-focused-final.xml").getroot().find("testsuite")
assert focused.attrib["failures"] == "0" and focused.attrib["errors"] == "0"
old_ruff = read("firmware-picker-ruff-before-import-fix.result.json")
old_ruff["raw"] = "firmware-picker-ruff-before-import-fix.txt"
(OUT / "firmware-picker-ruff-before-import-fix.result.json").write_text(
    json.dumps(old_ruff, indent=2) + "\n", encoding="utf-8"
)
firmware = read("eye-camera-firmware.json")
selected = read_firmware(firmware["sketch"])
assert selected.digest == firmware["sketch_snapshot_sha256"]
result = {
    "recorded_utc": datetime.now(timezone.utc).isoformat(),
    "source_revision": inputs["source_revision"],
    "source_state": "dirty working tree; preserve other owner/dev changes",
    "decisions": ["G01 revision 134", "A11 revision 42", "ARCH-002", "E15"],
    "changes": [
        "Remove displayed-MCU-failure-only Upload gate; retain idle/diagnostic/camera/native cleanup gates",
        "Include Eye ownership in controller MCU command admission",
    ],
    "full_suite_tested_inputs": "firmware-picker-inputs.json",
    "final_sha256": current,
    "post_suite_text_change": {
        "paths": drift,
        "description": "Ruff removes one import-separator blank line in owning test; no runtime source changed",
        "validation": "40 focused firmware cases pass again; final static checks pass",
    },
    "checks": checks,
    "declarations": declarations,
    "unchanged_contract_checks": {
        "source_snapshot": "eye-camera-inputs.json",
        "current_contract_tracking_visual_input_drift": contract_drift,
        "results": contract_checks,
        "scope": "Retained earlier checks on unchanged contract/Tracking/Visual source; not rerun during firmware-only repair",
    },
    "pytest": suite.attrib,
    "focused_pytest": focused.attrib,
    "native": {
        "method": "Computer-use sky: Browse native Uno firmware (*.ino *.hex) chooser, double-click selected repository ino, Test connection reproduces CAPS fault, Upload stays enabled, explicit Upload, Test connection again",
        "selected_path": "firmware/uno/cephvr2_mcu/cephvr2_mcu.ino",
        "selected_sketch_sha256": selected.digest,
        "prior_compile_provenance": firmware,
        "gui_upload_verified": True,
        "before": "firmware-picker-fault-status.json",
        "pending": "firmware-picker-after-upload.json",
        "after": "firmware-picker-verified-status.json",
        "observations": "firmware-picker-native-observations.txt",
        "normal_restart_shutdown": read("firmware-picker-restart-shutdown.json"),
        "runtime_generation": status["controller_generation"],
        "outcome": "GUI compile/verified flash succeeds; protocol 3 and stopped outputs confirmed; retest succeeds; cleanup no longer pending",
        "final_runtime": "repaired GUI remains open in Configuration; no diagnostics or capture active",
    },
    "retained_failed_attempts": [
        "firmware-picker-focused.xml: new test fixture Mock(spec=DeviceHooks) omitted dataclass fields; replace with explicit DeviceHooks before final passes",
        "firmware-picker-ruff-before-import-fix.txt: one test import separator; fixed",
        "firmware-picker-launcher.txt: existing runtime replacement prompt; no Kill consent given; reopen existing GUI, then normal shutdown and restart",
        "native picker indexed click was not in cached app state; reobserve and use screenshot coordinates successfully",
    ],
    "limits": "No new dummy recording, Eye triggering, electrical/timing/full-load or SpikeGLX acceptance. V20 pacing identity and Eye external wiring/source/rate remain unresolved.",
}
(OUT / "firmware-picker-context.json").write_text(
    json.dumps(result, indent=2) + "\n", encoding="utf-8"
)
print(json.dumps({"pytest": suite.attrib, "focused": focused.attrib, "drift": drift, "native": result["native"]["outcome"]}, indent=2))
