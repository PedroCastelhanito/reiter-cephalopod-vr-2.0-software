"""Reconstruct cohort-start generated Python from hash-verified source contracts."""
from pathlib import Path
import hashlib,json,subprocess
from grpc_tools import protoc
start=json.loads(Path('/tmp/cephvr-nongui-start-hashes.json').read_text())
prior=Path('/tmp/cephvr-nongui-prior-source')
base=Path('/tmp/cephvr-nongui-start-generation')
contracts=base/'contracts'; output=base/'src';output.mkdir(parents=True,exist_ok=True)
sources=[]
for name,digest in start.items():
 if not name.endswith('.proto'):continue
 old=prior/name
 data=old.read_bytes() if old.exists() else subprocess.check_output(['git','show','HEAD:'+name])
 assert hashlib.sha256(data).hexdigest()==digest,name
 target=base/name;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(data);sources.append(str(target))
result=protoc.main(['grpc_tools.protoc',f'-I{contracts}',f'--python_out={output}',f'--pyi_out={output}',f'--grpc_python_out={output}',*sorted(sources)])
assert result==0
checked=0
for p in output.rglob('*.py'):
 name=str(Path('src')/p.relative_to(output))
 if name not in start:continue
 assert hashlib.sha256(p.read_bytes()).hexdigest()==start[name],name
 destination=prior/name;destination.parent.mkdir(parents=True,exist_ok=True);destination.write_bytes(p.read_bytes());checked+=1
print(json.dumps({'proto_sources_verified':len(sources),'cohort_start_generated_python_hashes_matched':checked}))
