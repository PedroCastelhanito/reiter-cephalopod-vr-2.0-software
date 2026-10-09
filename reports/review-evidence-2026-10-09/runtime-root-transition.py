"""One-time authorized rig transition; retain immutable recovery bytes and originals."""

import ctypes
from ctypes import wintypes
from datetime import datetime, timezone
import hashlib
import json
import msvcrt
import os
from pathlib import Path

from cephvr.platform.windows.guard import SingleInstanceGuard
from cephvr.shared.credentials import _check_private, default_runtime_root
from cephvr.shared.recovery import RecoveryStore, _publish, _read

OUT = Path(__file__).resolve().parent
source_root = Path(os.environ["LOCALAPPDATA"]) / "CephVR2" / "runtime"
destination = default_runtime_root()
assert destination == Path(os.environ["USERPROFILE"]) / ".cephvr2" / "runtime"
assert source_root.resolve() != destination.resolve()

with SingleInstanceGuard("application"):
    _check_private(source_root, directory=True)
    assert not (source_root / "launcher.json").exists(), "old launcher endpoint remains"
    source = source_root / "recovery"
    _check_private(source, directory=True)
    target = RecoveryStore(destination).runtime_root
    payloads = {}
    for path in sorted(source.iterdir()):
        _check_private(path, directory=False)
        assert _read(path) is not None, path.name
        payload = path.read_bytes()
        assert len(payload) <= 4096, path.name
        if (target / path.name).exists():
            _check_private(target / path.name, directory=False)
            assert (target / path.name).read_bytes() == payload, "destination conflict"
        payloads[path.name] = payload
    for name, payload in payloads.items():
        if not (target / name).exists():
            _publish(target / name, payload)
        assert (target / name).read_bytes() == payload
        assert (source / name).read_bytes() == payload
    assert {path.name for path in target.iterdir()} == set(payloads)
    hashes = {name: hashlib.sha256(raw).hexdigest() for name, raw in payloads.items()}

    api = ctypes.WinDLL("kernel32", use_last_error=True)
    api.GetFinalPathNameByHandleW.argtypes = [wintypes.HANDLE, wintypes.LPWSTR, wintypes.DWORD, wintypes.DWORD]
    api.GetFinalPathNameByHandleW.restype = wintypes.DWORD
    with next(target.iterdir()).open("rb") as stream:
        final_path = ctypes.create_unicode_buffer(32768)
        length = api.GetFinalPathNameByHandleW(msvcrt.get_osfhandle(stream.fileno()), final_path, len(final_path), 0)
        assert 0 < length < len(final_path)
        physical_path = final_path.value
        assert physical_path.removeprefix("\\\\?\\") == str(Path(stream.name).resolve())

result = {
    "recorded_utc": datetime.now(timezone.utc).isoformat(),
    "source": str(source), "destination": str(target),
    "records_copied_or_verified": len(hashes), "sha256": hashes,
    "original_bytes_retained": True, "target_bytes_verified": True,
    "owner_only_verification": "Existing Windows ACL helpers on source, target and every record",
    "application_guard": "Exclusively held during preservation; no application can start concurrently",
    "physical_target_example": physical_path,
    "credentials_and_old_endpoint": "Not imported; fresh generation credentials are provisioned at new startup",
}
(OUT / "runtime-root-transition.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
print(json.dumps({key: value for key, value in result.items() if key != "sha256"}, indent=2))
