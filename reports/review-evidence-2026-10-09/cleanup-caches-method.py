"""Remove known project caches only after validation; preserve environment and evidence."""
import json
import os
import shutil
from pathlib import Path
root = Path.cwd()
names = {'__pycache__', '.pytest_cache', '.mypy_cache', '.ruff_cache'}
removed = []
for base, dirs, files in os.walk(root, followlinks=False):
    dirs[:] = [name for name in dirs if name not in {'.git', '.venv'}]
    for name in list(dirs):
        if name not in names:
            continue
        target = Path(base) / name
        if target.is_symlink():
            raise RuntimeError(f'Unexpected cache symlink: {target}')
        entries = [p for p in target.rglob('*') if p.is_file() and not p.is_symlink()]
        removed.append({'path': str(target.relative_to(root)), 'files': len(entries), 'bytes': sum(p.stat().st_size for p in entries)})
        shutil.rmtree(target)
        dirs.remove(name)
manifest = root / 'reports/review-evidence-2026-10-09/cleanup.json'
data = json.loads(manifest.read_text())
data['project_caches'] = {'method': 'After final verification, remove only named generated cache directories while excluding .git and .venv; no symlinks followed.', 'directories': len(removed), 'files': sum(x['files'] for x in removed), 'bytes': sum(x['bytes'] for x in removed), 'paths': removed}
manifest.write_text(json.dumps(data, indent=2) + '\n')
print(json.dumps({k:v for k,v in data['project_caches'].items() if k != 'paths'}, indent=2))
