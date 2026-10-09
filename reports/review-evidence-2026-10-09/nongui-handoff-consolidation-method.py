"""Consolidate exact-prefix handoff copies without discarding unique raw evidence."""
from pathlib import Path
import hashlib,json
base=Path('reports/review-evidence-2026-10-09')
replacements={};removed=[]
for source,pattern,destination in [('/tmp/cephvr-nongui-astra-review.txt','nongui-astra-*.txt','nongui-astra-review.txt'),('/tmp/cephvr-nongui-sol-owned-camera.txt','nongui-sol-owned-camera-*.txt','nongui-sol-owned-camera.txt')]:
 current=Path(source).read_bytes();target=base/destination;target.write_bytes(current)
 for old in sorted(base.glob(pattern)):
  if old==target:continue
  data=old.read_bytes()
  if not current.startswith(data):raise RuntimeError(f'Unique evidence must be retained: {old}')
  replacements[old.name]=destination
  removed.append({'path':str(old),'sha256':hashlib.sha256(data).hexdigest(),'bytes':len(data),'retained_in':str(target),'proof':'The removed file was a byte-identical prefix of retained raw handoff.'})
for p in [Path('LOG.md'),Path('TODO.md'),*Path('reports').rglob('*.md')]:
 content=p.read_text();updated=content
 for old,new in replacements.items():updated=updated.replace(old,new)
 if updated!=content:p.write_text(updated)
for entry in removed:Path(entry['path']).unlink()
manifest=base/'cleanup.json';data=json.loads(manifest.read_text());data['nongui_duplicate_handoffs']={'method':'Consolidate only byte-identical prefixes into complete raw model handoffs; update incoming report/log links; no unique findings/evidence lost.','files':len(removed),'bytes':sum(x['bytes'] for x in removed),'paths':removed};manifest.write_text(json.dumps(data,indent=2)+'\n')
print(json.dumps({'redundant_prefix_files_removed':len(removed),'bytes':sum(x['bytes'] for x in removed)}))
