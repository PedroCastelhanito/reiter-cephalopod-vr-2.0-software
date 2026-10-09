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
    'suite': [('tests', [PYTHON, '-m', 'pytest', 'tests', '-q', '-m', 'not rig', '-p', 'no:cacheprovider', '-rs', '--junitxml=' + str(OUT / 'windows-checkout-tests.xml')])],
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
    if group == 'finalize':
        inputs = json.loads((OUT / 'windows-checkout-inputs.json').read_text(encoding='utf-8'))
        drift = [p for p, expected in inputs['sha256'].items() if hashlib.sha256((ROOT / p).read_bytes()).hexdigest() != expected]
        assert not drift, drift
        commands = {}
        for items in GROUPS.values():
            for name, _ in items:
                file = f'windows-checkout-{name}.result.json'
                result = json.loads((OUT / file).read_text(encoding='utf-8'))
                assert result['returncode'] == 0, result
                commands[file] = result
        for name in ('tests', 'mypy'):
            file = OUT / f'windows-checkout-{name}-before-generation.result.json'
            result = json.loads(file.read_text(encoding='utf-8'))
            result['raw'] = f'windows-checkout-{name}-before-generation.txt'
            file.write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
        check = subprocess.run(['git', 'diff', '--check'], cwd=ROOT, capture_output=True, text=True)
        assert check.returncode == 0, check.stdout + check.stderr
        (OUT / 'windows-checkout-whitespace.txt').write_text(check.stdout + check.stderr, encoding='utf-8')
        commands['whitespace'] = {'command': ['git', 'diff', '--check'], 'returncode': check.returncode, 'raw': 'windows-checkout-whitespace.txt'}
        context = {'recorded_utc': datetime.now(timezone.utc).isoformat(), 'source_revision': inputs['source_revision'], 'source_state': 'Clean checkout initially; runtime/test/tool/contract/config validation inputs remain unchanged. Only root decision-index, reports, TODO/LOG and dated evidence are edited.', 'input_hashes': 'windows-checkout-inputs.json', 'input_files_unchanged': len(inputs['sha256']), 'commands': commands, 'declarations': 'windows-checkout-declarations.json', 'repair': 'Regenerated ignored local bindings with .venv/Scripts/python.exe tools/generate_contracts.py from 19 authoritative protos; corrected root V08/V17/V18 revision index to owning records.', 'failed_attempts': ['windows-checkout-tests-before-generation.result.json', 'windows-checkout-mypy-before-generation.result.json', 'windows-checkout-declarations-before-index-fix.json'], 'limitations': ['QT offscreen suite excludes the one rig-marked Tracking native test. Five symlink cases skip because account privilege/Developer Mode is unavailable.', 'Available device-independent native Windows checks ran; no physical camera capture, MCU serial/firmware, projector presentation, dummy protocol, SpikeGLX pairing or full workload acceptance rerun.', 'Initial temporary declaration check hit sandbox temp-directory permission denial; rerun uses workspace-owned temporary storage.', 'No handwritten runtime code, operator defaults or accepted decision behavior changed. No commit or push performed.']}
        (OUT / 'windows-checkout-context.json').write_text(json.dumps(context, indent=2) + '\n', encoding='utf-8')
        print(f"All commands pass; {len(inputs['sha256'])} tested inputs unchanged")
        return 0
    if group == 'snapshot':
        paths = subprocess.check_output(['git', 'ls-files', 'src', 'tests', 'tools', 'contracts', 'config', 'pyproject.toml'], cwd=ROOT, text=True).splitlines()
        payload = {'recorded_utc': datetime.now(timezone.utc).isoformat(), 'source_revision': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(), 'sha256': {p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest() for p in paths if (ROOT / p).is_file()}}
        (OUT / 'windows-checkout-inputs.json').write_text(json.dumps(payload, indent=2) + '\n', encoding='utf-8')
        print(f"Recorded {len(payload['sha256'])} validation inputs")
        return 0
    failed = False
    for name, command in GROUPS[group]:
        start = time.monotonic()
        recorded = datetime.now(timezone.utc).isoformat()
        with (OUT / f'windows-checkout-{name}.txt').open('w', encoding='utf-8') as log:
            result = subprocess.run(command, cwd=ROOT, env=ENV, stdout=log, stderr=subprocess.STDOUT)
        payload = {'command': command, 'environment': {'QT_QPA_PLATFORM': 'offscreen', 'PYTHONDONTWRITEBYTECODE': '1'}, 'started_utc': recorded, 'elapsed_seconds': round(time.monotonic() - start, 3), 'returncode': result.returncode, 'raw': f'windows-checkout-{name}.txt'}
        (OUT / f'windows-checkout-{name}.result.json').write_text(json.dumps(payload, indent=2) + '\n', encoding='utf-8')
        print(f'{name}: exit {result.returncode}, {payload["elapsed_seconds"]}s', flush=True)
        print((OUT / payload['raw']).read_text(encoding='utf-8')[-1800:], flush=True)
        failed |= bool(result.returncode)
    return int(failed)

if __name__ == '__main__':
    raise SystemExit(main())
