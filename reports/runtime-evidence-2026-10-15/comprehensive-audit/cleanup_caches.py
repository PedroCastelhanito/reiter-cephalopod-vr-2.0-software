"""Remove only reproducible, untracked repository caches after validation."""

import json
import os
from pathlib import Path
import shutil
import subprocess

root = Path.cwd().resolve()
out = Path(__file__).parent
candidates = [root / name for name in (".pytest_cache", ".ruff_cache", ".mypy_cache")]
for folder in (root / "src", root / "tests", root / "tools", out):
    for parent, directories, _ in os.walk(folder, followlinks=False):
        directories[:] = [name for name in directories if not (Path(parent)/name).is_symlink()]
        if "__pycache__" in directories:
            candidates.append(Path(parent) / "__pycache__")
            directories.remove("__pycache__")
record = []
for path in candidates:
    if not path.exists():
        continue
    assert not path.is_symlink() and not (path.stat().st_file_attributes & 0x400), path
    resolved = path.resolve()
    assert resolved.is_relative_to(root) and resolved != root
    assert path.name in {".pytest_cache", ".ruff_cache", ".mypy_cache", "__pycache__"}
    assert not subprocess.check_output(["git", "ls-files", "--", str(path.relative_to(root))], text=True).strip()
    files = []
    for parent, directories, names in os.walk(path, followlinks=False):
        for name in (*directories, *names):
            item = Path(parent) / name
            assert not item.is_symlink() and not (item.stat().st_file_attributes & 0x400), item
        files.extend(Path(parent)/name for name in names)
    row = {"path": str(path.relative_to(root)), "file_count": len(files), "bytes": sum(p.stat().st_size for p in files)}
    shutil.rmtree(path)
    row["removed"] = not path.exists()
    record.append(row)
    (out / "cache-cleanup.json").write_text(json.dumps(record, indent=2)+"\n")
print(json.dumps({"directories": len(record), "bytes": sum(row["bytes"] for row in record)}, indent=2))
