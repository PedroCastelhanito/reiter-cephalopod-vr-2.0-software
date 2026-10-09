"""Read-only packaged/unpackaged endpoint and N-branch visibility probe."""

import builtins
import ctypes
from ctypes import wintypes
from datetime import datetime, timezone
import json
import msvcrt
from pathlib import Path
import sys

from cephvr.launcher.replacement import (
    ReplacementDeclined, _existing_endpoint, acquire_application_guard,
)
from cephvr.shared.credentials import default_runtime_root

OUT = Path(__file__).resolve().parent
tag = sys.argv[1]
assert tag in {"packaged", "unpackaged"}
root = default_runtime_root()
api = ctypes.WinDLL("kernel32", use_last_error=True)
api.GetCurrentPackageFullName.argtypes = [ctypes.POINTER(wintypes.UINT), wintypes.LPWSTR]
api.GetCurrentPackageFullName.restype = wintypes.LONG
length = wintypes.UINT(0)
package_result = api.GetCurrentPackageFullName(ctypes.byref(length), None)
package = ""
if package_result == 122:
    buffer = ctypes.create_unicode_buffer(length.value)
    package_result = api.GetCurrentPackageFullName(ctypes.byref(length), buffer)
    assert package_result == 0
    package = buffer.value
else:
    assert package_result == 15700, package_result

before = _existing_endpoint(root)
api.GetFinalPathNameByHandleW.argtypes = [wintypes.HANDLE, wintypes.LPWSTR, wintypes.DWORD, wintypes.DWORD]
api.GetFinalPathNameByHandleW.restype = wintypes.DWORD
with (root / "launcher.json").open("rb") as stream:
    physical = ctypes.create_unicode_buffer(32768)
    result = api.GetFinalPathNameByHandleW(msvcrt.get_osfhandle(stream.fileno()), physical, len(physical), 0)
    assert 0 < result < len(physical)
    assert physical.value.removeprefix("\\\\?\\") == str((root / "launcher.json").resolve())

prompts = []
def decline(prompt):
    prompts.append(prompt)
    return "N"

builtins.input = decline
sys.stdin.isatty = lambda: True
try:
    acquired = acquire_application_guard(root)
except ReplacementDeclined as exc:
    outcome = str(exc)
else:
    acquired.close()
    raise AssertionError("Expected an already-running runtime")
after = _existing_endpoint(root)
assert before == after and len(prompts) == 1
result = {
    "recorded_utc": datetime.now(timezone.utc).isoformat(),
    "launch_tag": tag, "package_api_returncode": package_result,
    "package_full_name": package, "runtime_root": str(root),
    "physical_endpoint": physical.value,
    "controller_generation": before.controller_generation,
    "method": "Probe supplies interactive isatty/input=N to the real replacement function; no event is signaled",
    "prompt": prompts[0], "answer": "N", "outcome": outcome,
    "exact_endpoint_preserved": before == after,
}
(OUT / f"runtime-root-visibility-{tag}.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
print(json.dumps(result, indent=2))
