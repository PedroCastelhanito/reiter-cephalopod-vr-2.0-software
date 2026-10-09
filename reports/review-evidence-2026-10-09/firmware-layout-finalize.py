"""Reconcile source preservation and the layout-only check scope."""
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
compiled = read("firmware-layout-compile.json")
expected = {
    "cephvr1_mcu.ino": "8e7102b221e5cab65336e2b8450cc726e4dc5ce7710e18d5cea80b38fb65c41e",
    "cephvr2_mcu.ino": "5abce26e94630477058198b1f2bceb15797f91a7e352bcf9074f7687c69d0b36",
    "projector_clock.h": "dccfa8d4782b66793138d9ddcce55a62759be661c7e7f5f93c6c7d5467a6ab9c",
}
for name, result in compiled["results"].items():
    assert result["returncode"] == 0
    for relative, digest in result["source_sha256"].items():
        assert digest == expected[relative]
        assert hashlib.sha256((Path(result["source"]).parent / relative).read_bytes()).hexdigest() == digest
assert hashlib.sha256((ROOT / "firmware/projector_clock.h").read_bytes()).hexdigest() == expected["projector_clock.h"]
suite = ET.parse(OUT / "firmware-layout-owner-tests.xml").getroot()[0]
assert suite.attrib["tests"] == "69" and suite.attrib["skipped"] == "1"
assert suite.attrib["failures"] == suite.attrib["errors"] == "0"
declarations = read("firmware-layout-declarations.json")
assert not declarations["issues"]
status = read("firmware-layout-gui-status.json")
assert status["session"]["phase"] == "SESSION_PHASE_CONFIGURATION"
context = {
    "recorded_utc": datetime.now(timezone.utc).isoformat(),
    "source_revision": inputs["source_revision"], "decisions": ["A11 revision 42", "ARCH-002", "E15"],
    "repair": "Independent matching sketch folders plus legacy companion header; no backend/firmware source edits",
    "source_preservation": expected, "source_and_header_bytes_unchanged": True,
    "compiled": "firmware-layout-compile.json", "owner_tests": dict(suite.attrib),
    "owner_test_command": ".venv/Scripts/python.exe -m pytest tests/controller/test_microcontroller_owner.py -q -m 'not rig' --junitxml=reports/review-evidence-2026-10-09/firmware-layout-owner-tests.xml",
    "environment": {"QT_QPA_PLATFORM": "offscreen"},
    "unchanged_previous_test_inputs": len(inputs["sha256"]), "source_drift": drift,
    "full_suite_provenance": "Prior runtime-root tests/static results apply to byte-identical src/tests/tools/contracts/config inputs. No new full-suite/static run is claimed for firmware layout/doc edits.",
    "declarations": declarations,
    "native_gui": {
        "generation": status["controller_generation"], "window": 984278,
        "method": "Reopen fails because old owner event no longer exists (Win32 2). Verify application guard free, start fresh hidden helper 23468 with N fallback; no previous runtime is killed. Browse sees both matching directories. A set_value attempt cannot resolve cached dialog element; reobserve, coordinate-focus filename, type full path and accept Open.",
        "before_selection": "Persisted selection still pointed at moved firmware/uno/cephvr2_mcu.ino; activity retained missing-file rejection before repaired selection.",
        "accepted_path": str(ROOT / "firmware/uno/cephvr2_mcu/cephvr2_mcu.ino"),
        "outcome": "PathEdit reports new absolute path and Upload is enabled; idle Configuration status captured separately",
        "board_actions": "No Upload/Test connection/pin command issued by this task",
    },
    "limits": "Native compilation and picker pass. CephVR1 still lacks CAPS and is not protocol-3 host-compatible. No new flash, electrical check or experiment run.",
}
(OUT / "firmware-layout-context.json").write_text(json.dumps(context, indent=2) + "\n", encoding="utf-8")
print(f"Both compiled snapshots preserved; {len(inputs['sha256'])} previous tested inputs unchanged; 68 owner cases passed")
