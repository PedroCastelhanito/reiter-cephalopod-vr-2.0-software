import json
import subprocess
import sys
import tempfile
from pathlib import Path

out = Path(__file__).parent.resolve()
with tempfile.TemporaryDirectory(prefix='contract-check-', dir=out) as folder:
    generated = Path(folder).resolve()
    assert generated.is_relative_to(out)
    command = [sys.executable, 'tools/generate_contracts.py', '--output', str(generated)]
    process = subprocess.run(command, capture_output=True, text=True, timeout=60)
    assert process.returncode == 0, process.stderr
    checked = []
    drift = []
    for path in generated.rglob('*'):
        if path.is_file() and '_pb2' in path.name:
            relative = path.relative_to(generated)
            checked.append(str(relative))
            if path.read_bytes() != (Path('src') / relative).read_bytes():
                drift.append(str(relative))
    record = {'method': 'generate bindings in fresh isolated directory, compare generated pb2 files with source; generated source not edited', 'generator_exit': process.returncode, 'stdout': process.stdout, 'checked_count': len(checked), 'drift': drift}
    (out / 'closing-contracts.json').write_text(json.dumps(record, indent=2) + '\n')
    print(json.dumps(record))
    assert not drift
