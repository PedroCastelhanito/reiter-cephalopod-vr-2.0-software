"""Reconcile retained namespace-transition evidence against final source."""

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent

def read(name):
    return json.loads((OUT / name).read_text(encoding="utf-8-sig"))

inputs = read("runtime-root-inputs.json")
drift = [p for p, digest in inputs["sha256"].items()
         if hashlib.sha256((ROOT / p).read_bytes()).hexdigest() != digest]
assert not drift, drift
checks = {name: read(f"runtime-root-{name}.result.json")
          for name in ("tests", "ruff", "format", "mypy", "boundaries", "dependencies")}
assert all(r["returncode"] == 0 for r in checks.values())
suite = ET.parse(OUT / "runtime-root-tests.xml").getroot()[0]
focused = ET.parse(OUT / "runtime-root-focused.xml").getroot()[0]
assert (int(suite.attrib["tests"]), int(suite.attrib["skipped"])) == (1861, 5)
assert (int(focused.attrib["tests"]), int(focused.attrib["skipped"])) == (296, 1)
assert suite.attrib["failures"] == focused.attrib["failures"] == "0"
assert suite.attrib["errors"] == focused.attrib["errors"] == "0"

transition = read("runtime-root-transition.json")
for name, digest in transition["sha256"].items():
    for directory in ("source", "destination"):
        assert hashlib.sha256((Path(transition[directory]) / name).read_bytes()).hexdigest() == digest
assert len(transition["sha256"]) == 136

before = read("runtime-root-new-status.json")["controller_generation"]
after_n = read("runtime-root-after-N-status.json")["controller_generation"]
after_y = read("runtime-root-after-Y-status.json")["controller_generation"]
receipt = read("runtime-root-Y-exit-receipt.json")
assert before == after_n and before != after_y
assert receipt["controller_generation"] == before and receipt["all_owned_processes_absent"]
assert read("runtime-root-old-shutdown.json")["succeeded"]
assert read("runtime-root-test-shutdown.json")["succeeded"]
final = read("runtime-root-final-reopened-status.json")
assert final["controller_generation"] == read("runtime-root-final-status.json")["controller_generation"]
assert final["session"]["phase"] == "SESSION_PHASE_CONFIGURATION"

visibility = {tag: read(f"runtime-root-visibility-{tag}.json") for tag in ("packaged", "unpackaged")}
assert len({r["physical_endpoint"] for r in visibility.values()}) == 1
assert all(r["controller_generation"] == final["controller_generation"] and r["exact_endpoint_preserved"] for r in visibility.values())
declarations = read("runtime-root-declarations.json")
assert not declarations["issues"]

context = {
    "recorded_utc": datetime.now(timezone.utc).isoformat(),
    "source_revision": inputs["source_revision"],
    "source_state": "dirty working tree; preserve owner/dev and previous repairs",
    "decisions": ["E08 revision 170", "ARCH-002", "E15"],
    "changes": "Use shared absolute USERPROFILE namespace via existing root selector/private ACLs; retain exact event/receipt replacement",
    "tested_inputs": "runtime-root-inputs.json", "unchanged_input_count": len(inputs["sha256"]), "source_drift": drift,
    "checks": checks, "full_suite": dict(suite.attrib), "focused": dict(focused.attrib),
    "exclusions": "Five symlink-privilege skips, one explicitly rig-marked deselection; QT_QPA_PLATFORM=offscreen",
    "declarations": declarations,
    "preservation": {"raw": "runtime-root-transition.json", "records": 136, "original_and_target_hashes_rechecked": True},
    "live_replacement": {
        "method": "Native exec PTY runs owner's exact base-Python command; real terminal input N then Y in separate launches",
        "command": "C:\\Users\\ReiterU_PC\\miniforge3\\python.exe scripts/start_runtime_gui.py",
        "N": {"before": before, "after": after_n, "outcome": "Existing runtime left running.", "exit_code": 0},
        "Y": {"before": before, "after": after_y, "receipt": "runtime-root-Y-exit-receipt.json", "all_owned_processes_absent": True},
        "test_replacement_shutdown": "runtime-root-test-shutdown.json",
        "final_generation": final["controller_generation"], "final_phase": final["session"]["phase"],
        "final_reopen": "scripts/start_runtime_gui.py --reopen-gui exits 0; same controller generation, native dashboard window 3933604",
        "gui_observation": "Retained-event notice acknowledged with native coordinate click; Controller connected, take_control Completed, Control held in Configuration",
        "early_final_attempt": "Prompt appeared before former launcher finished exiting. Verify free application guard, then retire only task-created waiting helper 20836 after matching parent 24672, executable, command and 16:49:57 creation time. Wrappers 6376/25524/24672 exit. Preserve final-launcher logs; successful retry uses N stdin fallback and never implicit Y.",
    },
    "visibility": visibility,
    "visibility_scope": "packaged tag means Codex child shell, unpackaged tag means hidden Shell.Application.ShellExecute helper. Both API returns 15700 (no package identity). These helper probes inject interactive input=N into the real replacement function, distinct from live PTY tests; owner's own terminal not manually retested.",
    "limits": "No new experiment, hardware timing, third Eye trigger wiring or SpikeGLX pairing acceptance. Existing V20 pacing warning remains. Retained controller operation 09e718b2-9c6b-4a19-b133-38f3a17f1cbe reports legacy ino compilation missing projector_clock.h; no firmware command is issued during this task.",
}
(OUT / "runtime-root-context.json").write_text(json.dumps(context, indent=2) + "\n", encoding="utf-8")
print(f"Final: {len(inputs['sha256'])} unchanged inputs, 136 preserved records, 1856+295 passing cases; no reconciliation issues")
