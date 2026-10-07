"""Inject loss of one observed test GUI using retained exact native identity."""

import json
import subprocess
import time
from pathlib import Path

from cephvr.platform.windows.jobs import (
    PROCESS_QUERY_LIMITED_INFORMATION,
    SYNCHRONIZE,
    WindowsJobs,
)

OUT = Path(__file__).parent
ROOT = OUT.parents[1]
prior = json.loads((OUT / "relaunch-prior-gui.json").read_text(encoding="utf-8-sig"))
native = WindowsJobs()
pid = prior["ProcessId"]
handle = native.api.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION | SYNCHRONIZE, False, pid)
if not handle:
    raise RuntimeError("The observed test GUI cannot be inspected")
try:
    identity = native._member(handle, pid)
finally:
    native.api.CloseHandle(handle)
if identity is None or Path(identity[2]) != ROOT / ".venv/Scripts/cephvr-python.exe":
    raise RuntimeError("Observed GUI native identity differs")
native.retain_exact(*identity)
try:
    native.terminate_exact(identity[0], identity[1])
    deadline = time.monotonic() + 10
    while native.process_running(identity[0], identity[1]) and time.monotonic() < deadline:
        time.sleep(0.1)
    result = {"prior_identity": identity, "exact_prior_absent": not native.process_running(identity[0], identity[1])}
    (OUT / "relaunch-loss.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    if not result["exact_prior_absent"]:
        raise RuntimeError("The prior GUI exit remains unknown")
finally:
    native.release_process(identity[0], identity[1])
with (OUT / "relaunch-request.log").open("w", encoding="utf-8") as log:
    reopened = subprocess.run(
        [str(ROOT / ".venv/Scripts/python.exe"), "scripts/start_runtime_gui.py", "--reopen-gui"],
        cwd=ROOT, stdout=log, stderr=subprocess.STDOUT, timeout=20,
    )
print(json.dumps({**result, "reopen_request_exit_code": reopened.returncode}, indent=2))
