"""Reproduce checkout verification and retain exact commands and raw outcomes."""

import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
PYTHON = str(ROOT / '.venv/Scripts/python.exe')
ENV = dict(os.environ, QT_QPA_PLATFORM='offscreen', PYTHONDONTWRITEBYTECODE='1')
GROUPS = {
    'suite': [('tests', [PYTHON, '-m', 'pytest', 'tests', '-q', '-m', 'not rig', '-p', 'no:cacheprovider', '-rs', '--junitxml=' + str(OUT / 'runtime-root-tests.xml')])],
    'static': [
        ('ruff', [PYTHON, '-m', 'ruff', 'check', 'src', 'tests', 'tools', '--no-cache']),
        ('format', [PYTHON, '-m', 'ruff', 'format', '--check', 'src', 'tests', 'tools', '--no-cache']),
        ('mypy', [PYTHON, '-m', 'mypy', '--platform', 'win32', 'src/cephvr']),
        ('boundaries', [PYTHON, 'tools/check_backend_boundaries.py']),
        ('dependencies', [PYTHON, '-m', 'pip', 'check']),
    ],
    'contracts': [
        ('tracking-contracts', [PYTHON, '-m', 'unittest', 'discover', '-s', 'contracts/tracking', '-p', 'test_*.py']),
        ('visual-contracts', [PYTHON, '-m', 'unittest', 'discover', '-s', 'contracts/visual_stimulus/tests', '-p', 'test_*.py']),
        ('tracking-schema', [PYTHON, 'contracts/tracking/schema_check.py']),
        ('visual-schema', [PYTHON, 'contracts/visual_stimulus/generate_schemas.py', '--check']),
    ],
}

def main():
    group = sys.argv[1]
    if group == 'snapshot':
        paths = subprocess.check_output(['git', 'ls-files', 'src', 'tests', 'tools', 'contracts', 'config', 'pyproject.toml'], cwd=ROOT, text=True).splitlines()
        payload = {'recorded_utc': datetime.now(timezone.utc).isoformat(), 'source_revision': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(), 'sha256': {p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest() for p in paths if (ROOT / p).is_file()}}
        (OUT / 'runtime-root-inputs.json').write_text(json.dumps(payload, indent=2) + '\n', encoding='utf-8')
        print(f"Recorded {len(payload['sha256'])} validation inputs")
        return 0
    failed = False
    for name, command in GROUPS[group]:
        start = time.monotonic()
        recorded = datetime.now(timezone.utc).isoformat()
        with (OUT / f'runtime-root-{name}.txt').open('w', encoding='utf-8') as log:
            result = subprocess.run(command, cwd=ROOT, env=ENV, stdout=log, stderr=subprocess.STDOUT)
        payload = {'command': command, 'environment': {'QT_QPA_PLATFORM': 'offscreen', 'PYTHONDONTWRITEBYTECODE': '1'}, 'started_utc': recorded, 'elapsed_seconds': round(time.monotonic() - start, 3), 'returncode': result.returncode, 'raw': f'runtime-root-{name}.txt'}
        (OUT / f'runtime-root-{name}.result.json').write_text(json.dumps(payload, indent=2) + '\n', encoding='utf-8')
        print(f'{name}: exit {result.returncode}, {payload["elapsed_seconds"]}s', flush=True)
        print((OUT / payload['raw']).read_text(encoding='utf-8')[-1800:], flush=True)
        failed |= bool(result.returncode)
    return int(failed)

if __name__ == '__main__':
    raise SystemExit(main())


