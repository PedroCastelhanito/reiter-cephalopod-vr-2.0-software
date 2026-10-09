"""Join exact current verification inputs with raw native evidence and limits."""
import hashlib
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
import xml.etree.ElementTree as ET

out = Path(__file__).resolve().parent
root = out.parents[1]
inputs = json.loads((out / "eye-camera-inputs.json").read_text())
mismatches = [name for name, digest in inputs["sha256"].items() if hashlib.sha256((root / name).read_bytes()).hexdigest() != digest]
for name, snapshot in [("before-recheck", "before-mcu-pins"), ("before-terminal-fix", "before-terminal-fix")]:
    path = out / f"eye-camera-tests-{name}.result.json"
    result = json.loads(path.read_text())
    result["raw"] = f"eye-camera-tests-{name}.txt"
    result["source_inputs"] = f"eye-camera-inputs-{snapshot}.json"
    path.write_text(json.dumps(result, indent=2) + "\n")
suite = ET.parse(out / "eye-camera-tests.xml").getroot().find("testsuite")
checks = {name: json.loads((out / f"eye-camera-{name}.result.json").read_text()) for name in ["tests", "ruff", "format", "mypy", "boundaries", "dependencies", "tracking-contracts", "visual-contracts", "tracking-schema", "visual-schema"]}
status = json.loads((out / "eye-camera-final-status.json").read_text(encoding="utf-8-sig"))
shutdown = json.loads((out / "eye-camera-final-shutdown.json").read_text(encoding="utf-8-sig"))
context = {
    "recorded_utc": datetime.now(timezone.utc).isoformat(),
    "base_revision": inputs["source_revision"],
    "source_scope": "Uncommitted working tree; prior user/dev changes preserved; tracked inputs in eye-camera-inputs.json",
    "input_count": len(inputs["sha256"]), "source_mismatches": mismatches,
    "checks": checks, "pytest": dict(suite.attrib),
    "declarations": "eye-camera-declarations.json",
    "native": {
        "method": "Computer-use sky UI: refreshed inventory, Test enabled, Eye role assignment attempt, MCU Test connection; authenticated CLI status and normal shutdown; isolated SerialOwner probe only after normal shutdown",
        "final_generation": status["controller_generation"],
        "serials": {"behavioral": "40065509", "tracking": "40747103", "third_discovered_unassigned": "40278236"},
        "camera_identity_gui": "Both existing cameras report connection and identity verified before and after terminal-ack repair",
        "final_launcher_errors": (out / "eye-camera-final-launcher-error.txt").read_text(),
        "operations": status["operations"], "microcontroller": status["microcontroller"], "normal_shutdown": shutdown,
        "legacy_probe": "eye-camera-mcu-probe.json", "firmware_review": "eye-camera-firmware.json",
        "eye_assignment": "Rejected by unrelated saved Visual Stimulus profile: pulse disabled, no pacing output; no assignment committed",
        "recordings": "No new camera/stimulus capture or trial recording. Historical run43 remains separately retained; velocities disabled, no SpikeGLX pairing",
    },
    "intermediate_attempts": [
        "525 focused: 521 pass/four regressions (three layout plus all-role fixture); corrected, eight focused cases pass",
        "Eye preview scope lookup missing: corrected, seven focused cases pass",
        "First full suite: 1832 pass/one 2 s async wait failure; unchanged two variants pass in isolation; subsequent full passes 1833 and 1835; final 1843",
        "Initial native CLI shutdown rejected because GUI held control; explicit takeover followed by normal shutdown succeeded",
        "Original MCU Connect timeout diagnosed using raw legacy replies; final host rejects unsupported CAPS immediately",
    ],
    "pending": ["Eye external wiring/source/rate/topology and trigger integration", "V20 explicit pacing output", "Explicit protocol-3 upload authorization under firmware deferral", "New dummy/output checks after blockers resolved; optical/electrical/full-load/scientific acceptance remains open"],
}
(out / "eye-camera-context.json").write_text(json.dumps(context, indent=2) + "\n")
print(json.dumps({"inputs":len(inputs["sha256"]), "mismatches":mismatches, "pytest":dict(suite.attrib), "failed_checks":[name for name,result in checks.items() if result["returncode"]], "shutdown":shutdown}, indent=2))
raise SystemExit(bool(mismatches) or any(result["returncode"] for result in checks.values()))
