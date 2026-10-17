"""Preserve the inherited dirty checkout and operator settings before this audit."""

import hashlib
import json
from pathlib import Path
import subprocess
import time
import zipfile

root = Path.cwd()
out = Path(__file__).parent
assert not (out / "baseline.json").exists()
changed = subprocess.check_output(["git", "diff", "--name-only"], text=True).splitlines()
untracked = subprocess.check_output(["git", "ls-files", "--others", "--exclude-standard"], text=True).splitlines()
paths = sorted(set(changed + [p for p in untracked if not (root/p).is_relative_to(out)]))
record = {"date": "2026-10-17", "observed_unix_time": time.time(), "head": subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(), "inherited_files": {}, "operator_files": {}}
with zipfile.ZipFile(out / "inherited-baseline.zip", "x", compression=zipfile.ZIP_DEFLATED) as backup:
    for relative in paths:
        path = root/relative
        if path.is_file():
            content = path.read_bytes()
            backup.writestr(relative, content)
            record["inherited_files"][relative] = {"bytes": len(content), "sha256": hashlib.sha256(content).hexdigest()}
(out/"inherited.patch").write_bytes(subprocess.check_output(["git", "diff", "--binary"]))
(out/"original-settings").mkdir()
for path in [root/"config/last_configuration.json", root/"config/runtime_gui.json", *sorted((root/"config/backends").glob("*.toml"))]:
    if path.is_file():
        content = path.read_bytes()
        (out/"original-settings"/path.name).write_bytes(content)
        record["operator_files"][str(path.relative_to(root))] = {"bytes": len(content), "sha256": hashlib.sha256(content).hexdigest()}
(out/"baseline.json").write_text(json.dumps(record, indent=2)+"\n", encoding="utf-8")
print(json.dumps({"head": record["head"], "inherited_files": len(record["inherited_files"]), "operator_files": len(record["operator_files"])}, indent=2))
