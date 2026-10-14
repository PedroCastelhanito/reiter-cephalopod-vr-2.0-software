import hashlib
import json
import re
import subprocess
import tomllib
from pathlib import Path


root = Path(__file__).parent
tomls = sorted(Path('config/backends').glob('*.toml')) + sorted(Path('contracts/policy').glob('*.toml'))
for path in tomls:
    tomllib.loads(path.read_text(encoding='utf-8'))
schemas = sorted(Path('contracts').rglob('*.schema.json'))
for path in schemas:
    schema = json.loads(path.read_text(encoding='utf-8'))
    assert isinstance(schema, dict), path
documents = [Path(p) for p in ('reports/runtime.md', 'reports/acquisition.md', 'reports/visual_stimulus.md', 'reports/rig-verification.md', 'TODO.md', 'architecture.md', 'docs/architecture/gui.md')]
new_links = []
for path in documents:
    text = path.read_bytes().decode('utf-8', errors='surrogateescape')
    for target in re.findall(r'\]\(([^)]+)\)', text):
        if 'rig-timing-audit' not in target:
            continue
        resolved = path.parent / target.split('#')[0]
        assert resolved.is_file(), (path, target)
        new_links.append({'document': str(path), 'target': target})
assert (Path('config/backends/visual_stimulus_config.toml').read_bytes() == (root / 'visual_stimulus_config.toml.before').read_bytes())
assert tomllib.loads(Path('config/backends/acquisition_config.toml').read_text())['buffers']['recording_queue_frames'] == 17
changed = subprocess.run(['git', 'diff', '--name-only'], capture_output=True, text=True, check=True).stdout.splitlines()
hashes = {name: hashlib.sha256(Path(name).read_bytes()).hexdigest() for name in changed if Path(name).is_file()}
record = {'scope': 'final source snapshot, dirty tree includes pre-existing work; earlier rig generations did not run all final fixes', 'source_revision': subprocess.run(['git', 'rev-parse', 'HEAD'], capture_output=True, text=True, check=True).stdout.strip(), 'source_sha256': hashes, 'toml_parse_count': len(tomls), 'json_schema_syntax_count': len(schemas), 'new_report_links_validated': new_links, 'visual_config_byte_exact_original': True, 'camera_queue_frames': 17, 'delegated_visual_final': {'agent': '/root/regression_triage', 'command': 'python -m pytest tests/visual_stimulus -q', 'outcome': '311 passed in2.56s', 'reason': 'explicit prior-catalogue retirement added to owning CPU preparation fixture', 'limit': 'source/local tests; no native projector acceptance'}, 'final_shutdown': json.loads((root / 'final-exit-receipt.json').read_text())}
(root / 'final-provenance.json').write_text(json.dumps(record, indent=2) + '\n')
for name in ('closing-visual.log', 'closing-visual.xml'):
    p = root / name
    if p.exists():
        p.rename(root / name.replace('closing-visual', 'closing-visual-before-fixture-retirement'))
print('TOMLs', len(tomls), 'schemas', len(schemas), 'report links', len(new_links), 'visual defaults exact; queue17; final provenance saved')
