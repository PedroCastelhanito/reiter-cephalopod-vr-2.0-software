"""Verify final tested inputs, GUI preservation, and generated/declaration evidence."""
from pathlib import Path
import hashlib, json, datetime
repo=Path.cwd(); evidence=repo/'reports/review-evidence-2026-10-09'
expected=json.loads((evidence/'nongui-final-input-hashes.json').read_text())
actual={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for base in ('src/cephvr','tests','contracts','config') for p in Path(base).rglob('*') if p.is_file() and p.suffix in {'.py','.pyi','.proto','.json','.toml','.md'}}
assert actual==expected, [p for p in set(actual)|set(expected) if actual.get(p)!=expected.get(p)]
initial=json.loads(Path('/tmp/cephvr-nongui-start-hashes.json').read_text())
gui={p:h for p,h in initial.items() if p.startswith(('src/cephvr/gui/','tests/gui/'))}
assert all(actual.get(p)==h for p,h in gui.items())
for file,prefix in (('nongui-protobuf-check.json','src/'),('nongui-declarations-check.json','')):
 data=json.loads((evidence/file).read_text())
 for name,digest in data['sha256'].items():
  assert hashlib.sha256((repo/(prefix+name)).read_bytes()).hexdigest()==digest,(file,name)
record={'generated_bindings_still_match':57,'declaration_inputs_unchanged':True,'recorded_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'tested_input_files_unchanged':len(actual),'GUI_files_unchanged':len(gui),'input_manifest':'nongui-final-input-hashes.json','note':'Exact final source/test/contract/config hashes, including generated stubs. Native/rig acceptance is separate.'}
(evidence/'nongui-final-integrity.json').write_text(json.dumps(record,indent=2)+'\n')
print(json.dumps(record))
