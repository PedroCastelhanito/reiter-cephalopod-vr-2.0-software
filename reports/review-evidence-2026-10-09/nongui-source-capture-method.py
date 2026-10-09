"""Capture exact cohort source changes after implementations and checks settle."""
from pathlib import Path
import json,hashlib,subprocess,difflib
repo=Path.cwd();evidence=repo/'reports/review-evidence-2026-10-09';start=json.loads(Path('/tmp/cephvr-nongui-start-hashes.json').read_text());prior=Path('/tmp/cephvr-nongui-prior-source')
suffixes={'.py','.proto','.json','.toml','.md'}
current={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for base in ('src/cephvr','tests','contracts','config') for p in Path(base).rglob('*') if p.is_file() and p.suffix in suffixes}
changes=[name for name in sorted(set(start)|set(current)) if start.get(name)!=current.get(name)]
assert not [x for x in changes if x.startswith(('src/cephvr/gui/','tests/gui/'))]
patch=[];hashes={};prior_hashes={};unavailable={}
for name in changes:
 before=b''
 if name in start:
  stored=prior/name
  if stored.exists():before=stored.read_bytes()
  else:before=subprocess.check_output(['git','show','HEAD:'+name])
  if hashlib.sha256(before).hexdigest()!=start[name]:
   assert name=='tests/acquisition/test_worker_foundations.py', name+' unexpected baseline mismatch'
   after=Path(name).read_bytes()
   supplement='nongui-worker-foundations-head.patch'
   (evidence/supplement).write_text(''.join(difflib.unified_diff(before.decode().splitlines(keepends=True),after.decode().splitlines(keepends=True),fromfile='a/'+name,tofile='b/'+name)))
   unavailable[name]={'declared_start_sha256':start[name],'final_sha256':current[name],'known_HEAD_sha256':hashlib.sha256(before).hexdigest(),'supplement':supplement,'limitation':'Exact dirty cohort before-state unavailable. Supplement is HEAD-to-final and may include earlier edits; excluded from cohort patch.'}
   hashes[name]=current[name]
   continue
  prior_hashes[name]=start[name]
 after=Path(name).read_bytes() if name in current else b''
 hashes[name]=current.get(name)
 patch.extend(difflib.unified_diff(before.decode().splitlines(keepends=True),after.decode().splitlines(keepends=True),fromfile='a/'+name if name in start else '/dev/null',tofile='b/'+name if name in current else '/dev/null'))
(evidence/'nongui-source.patch').write_text(''.join(patch))
(evidence/'nongui-source-hashes.json').write_text(json.dumps({'base_revision':subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),'method':'Cohort source diff from hashed start; pre-existing dirty files reconstructed from previous implementation patch and hash-verified; otherwise HEAD matched. Includes source/tests/contracts/config, excludes reports and architecture narrative. No GUI source/test change. One unavailable dirty test baseline is excluded and separately preserved as an explicitly labelled HEAD-to-final supplement.','baseline_unavailable':unavailable,'start_sha256':prior_hashes,'final_sha256':hashes,'gui_files_unchanged':sum(name.startswith(('src/cephvr/gui/','tests/gui/')) for name in start)},indent=2)+'\n')
print(json.dumps({'changed_paths':len(changes),'patch_bytes':sum(len(x.encode()) for x in patch)}))
