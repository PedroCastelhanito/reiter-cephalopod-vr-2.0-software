"""Retain source hashes and the actual scope of this dated evidence bundle."""
import hashlib
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

OUT = Path(__file__).resolve().parent
ROOT = OUT.parents[2]
paths = [
    "src/cephvr/controller/assembly.py",
    "src/cephvr/controller/control/configuration.py",
    "src/cephvr/controller/lifecycle/commands.py",
    "src/cephvr/gui/components.py",
    "src/cephvr/gui/devices.py",
    "src/cephvr/gui/projector_timing.py",
    "src/cephvr/gui/projector_reference.py",
    "src/cephvr/gui/protocol.py",
    "src/cephvr/gui/protocol_controls.py",
    "src/cephvr/gui/batch_create.py",
    "src/cephvr/gui/recordings.py",
    "src/cephvr/gui/managed_close.py",
    "tests/gui/test_dashboard.py",
    "tests/controller/test_configuration_transactions.py",
    "tests/controller/test_lifecycle_commands.py",
]
context = {
    "captured_utc": datetime.now(timezone.utc).isoformat(),
    "source_revision": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
    "source_scope": "dirty working tree with pre-existing concurrent edits preserved; hashes are the tested files, not an isolated commit",
    "source_sha256": {p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest() for p in paths},
    "python": ".venv/Scripts/python.exe (Python 3.11)",
    "commands": [
        "pytest tests/gui -q --basetemp=.tmp/gui-backend-dummy-baseline --junitxml=.../gui-baseline.xml",
        "pytest tests -q -m 'not rig' --basetemp=.tmp/gui-backend-full --junitxml=.../full-tests.xml",
        "pytest tests/gui -q --basetemp=.tmp/gui-dummy-final-suite --junitxml=.../gui-final.xml",
        "ruff check src/cephvr/gui src/cephvr/controller tests/gui tests/controller",
        "ruff format --check src/cephvr/gui src/cephvr/controller tests/gui tests/controller",
        "mypy --platform win32 src/cephvr/gui src/cephvr/controller",
        "tools/check_backend_boundaries.py",
        "git diff --check",
    ],
    "tests": {"baseline_gui": "326 passed, 8 failed", "first_full": "1560 passed, 2 failed, 5 skipped, 1 rig deselected; GUI failures repaired afterward", "gui_after_labels": "334 passed", "close_and_labels_focus": "10 passed, 328 deselected", "history_focus": "47 passed, 1 skipped", "final_full": "1566 passed, 5 skipped, 1 rig deselected in 171.33 seconds; includes all 338 GUI cases"},
    "environment": "Windows; QT_QPA_PLATFORM=offscreen for pytest; native/loopback checks elevated through managed approval; one initial sandboxed run stalled and exact test processes were stopped",
    "native": "actual GUI dispatch camera checks/capture/disconnect and MCU connection; SpikeGLX read-only diagnostic; normal shutdown-save/reload/restore with exact receipts; wide GUI inspection",
    "protocol": "dummy-assets/dummy_protocol.json: 60-second open-loop grating, Desktop output, both camera videos and stimulus video selected, velocities disabled",
    "experiment": "not run; configuration submission/real Setup denied by automatic approval review; pure validation rejects unset V20 pacing output; SpikeGLX acquisition already running and pulse inventory empty",
    "pending": "owner answers for pairing and pacing; approval/prerequisites for real Setup; native narrow/DPI and optical/electrical/scientific/full-load acceptance",
}
targets = [
    "reports/runtime.md",
    "reports/rig-verification.md",
    "docs/architecture/gui.md",
    "docs/architecture/experiment.md",
    "docs/architecture/visual_stimulus.md",
    "reports/rig-wiring-evidence-2026-10-08/dummy-experiment/final-all.xml",
    "reports/rig-wiring-evidence-2026-10-08/dummy-experiment/live-features.json",
    "reports/rig-wiring-evidence-2026-10-08/dummy-experiment/pure-validation.json",
]
assert all((ROOT / p).is_file() for p in targets)
assert "## Current scope and review" in (ROOT / targets[0]).read_text(encoding="utf-8")
for path, anchor in zip(targets[2:5], ("g02", "e07", "v20")):
    assert f'id="{anchor}"' in (ROOT / path).read_text(encoding="utf-8")
context["new_report_target_checks"] = "all targets and G02/E07/V20/current-scope anchors pass"
(OUT / "context.json").write_text(json.dumps(context, indent=2), encoding="utf-8")
print("Context and source hashes retained")
