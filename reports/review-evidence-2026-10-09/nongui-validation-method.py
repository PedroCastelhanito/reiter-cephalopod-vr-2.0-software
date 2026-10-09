"""Save exact commands/results for final portable checks; never run rig tests."""
from pathlib import Path
import datetime
import json
import os
import subprocess
import sys
import time

repo = Path.cwd()
evidence = repo / 'reports/review-evidence-2026-10-09'
python = str(repo / '.venv/bin/python')
commands = {
    'portable-suite': [python, '-m', 'pytest', 'tests', '-q', '-m', 'not windows and not rig', '-p', 'no:cacheprovider', '--junitxml=' + str(evidence / 'nongui-portable-suite.xml')],
    'ruff': [python, '-m', 'ruff', 'check', 'src', 'tests', 'tools', '--no-cache'],
    'format': [python, '-m', 'ruff', 'format', '--check', 'src', 'tests', 'tools', '--no-cache'],
    'mypy-win32': [python, '-m', 'mypy', '--platform', 'win32', '--cache-dir', '/tmp/cephvr-nongui-mypy-final', 'src/cephvr'],
    'boundaries': [python, 'tools/check_backend_boundaries.py'],
    'tracking-contracts': [python, '-m', 'unittest', 'discover', '-s', 'contracts/tracking', '-p', 'test_*.py'],
    'visual-contracts': [python, '-m', 'unittest', 'discover', '-s', 'contracts/visual_stimulus/tests', '-p', 'test_*.py'],
    'tracking-schema': [python, 'contracts/tracking/schema_check.py'],
    'visual-schema': [python, 'contracts/visual_stimulus/generate_schemas.py', '--check'],
    'doc-links': [python, '/tmp/cephvr-check-final-doc-links.py'],
    'whitespace': ['git', 'diff', '--check'],
}
env = dict(os.environ, PYTHONDONTWRITEBYTECODE='1', QT_QPA_PLATFORM='offscreen')
failed = False
for name in sys.argv[1:]:
    command = commands[name]
    started = datetime.datetime.now(datetime.timezone.utc).isoformat()
    before = time.monotonic()
    result = subprocess.run(command, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    path = evidence / ('nongui-' + name + '.txt')
    path.write_text(result.stdout)
    metadata = {'command': command, 'environment': {'PYTHONDONTWRITEBYTECODE': '1', 'QT_QPA_PLATFORM': 'offscreen'}, 'started_utc': started, 'elapsed_seconds': round(time.monotonic() - before, 3), 'returncode': result.returncode, 'raw': path.name}
    path.with_suffix('.result.json').write_text(json.dumps(metadata, indent=2) + '\n')
    print(json.dumps(metadata), flush=True)
    print(result.stdout[-2200:], flush=True)
    failed |= bool(result.returncode)
raise SystemExit(failed)
