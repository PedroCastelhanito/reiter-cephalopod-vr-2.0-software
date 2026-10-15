"""Reviewed cleanup of one unstarted audit artifact; never production recovery proof."""

import hashlib
import json
import os
from pathlib import Path
import stat

from cephvr.platform.windows.paths import extended_path, logical_path

root = Path.cwd()
out = Path(__file__).parent
backup = out / "quarantine-before-remediation"
backup.mkdir(exist_ok=False)
generation = "aeeeb20a-4ba2-4584-918e-e181a3dbcb9b"
session = "a83a2f34-7e49-4c8f-b74f-ecc12c8d56b5"
receipt = json.loads((out / "renderer-budget-exit.json").read_text())
assert receipt["controller_generation"] == generation and receipt["all_owned_processes_absent"]
processes = json.loads((out / "before-quarantine-cleanup-processes.json").read_text(encoding="utf-8-sig"))
if isinstance(processes, dict):
    processes = [processes]
assert not any("cephvr" in p["Name"].lower() for p in processes)
parent = out / "recordings" / "20261015_comprehensive_audit_textures60-cq23-fixed-r2"
assert parent.resolve().is_relative_to(root.resolve())
candidates = [p for p in parent.iterdir() if p.name.startswith(".DUMMY-175717.") and p.name.endswith(".cleanup")]
assert len(candidates) == 1
target = Path(extended_path(candidates[0]))
attributes = target.lstat()
assert stat.S_ISDIR(attributes.st_mode) and not attributes.st_file_attributes & stat.FILE_ATTRIBUTE_REPARSE_POINT
entries = sorted(target.iterdir())
assert {p.name for p in entries} == {".cephvr-reservation.json", ".cephvr.lock"}
record = {"scope": "Explicit cleanup of this audit's failed pre-StartSession artifact after exact process absence; not general recovery acceptance", "logical_target": str(logical_path(target)), "session":session,"generation":generation,"receipt":receipt,"files":[]}
for path in entries:
    info = path.lstat()
    assert stat.S_ISREG(info.st_mode) and not info.st_file_attributes & stat.FILE_ATTRIBUTE_REPARSE_POINT
    content = path.read_bytes()
    (backup / path.name).write_bytes(content)
    assert (backup / path.name).read_bytes() == content
    record["files"].append({"name":path.name,"size":len(content),"sha256":hashlib.sha256(content).hexdigest(),"attributes":info.st_file_attributes})
marker = target / ".cephvr-reservation.json"
content = marker.read_bytes()
data = json.loads(content)
assert data["controller_generation"] == generation and data["session_id"] == session and data["complete"] is False
assert (target / ".cephvr.lock").stat().st_size == 0
(backup / "context.json").write_text(json.dumps(record,indent=2)+"\n",encoding="utf-8")
expected = next(r["sha256"] for r in record["files"] if r["name"] == marker.name)
assert hashlib.sha256(marker.read_bytes()).hexdigest() == expected
os.unlink(marker)
record["removed_only_marker"] = not marker.exists()
record["remaining"] = [p.name for p in target.iterdir()]
assert record["remaining"] == [".cephvr.lock"]
(out / "quarantine-remediation.json").write_text(json.dumps(record,indent=2)+"\n",encoding="utf-8")
print(json.dumps(record,indent=2))
