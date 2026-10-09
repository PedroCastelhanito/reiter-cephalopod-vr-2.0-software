from pathlib import Path
import hashlib,json,shutil,subprocess
root=Path.cwd(); scratch=root/'.tmp'
assert scratch.is_dir() and not scratch.is_symlink()
files=[p for p in scratch.rglob('*') if p.is_file()]
assert len(files)==10353, 'scratch changed since inventory'
retained={
 'gui_snapshots_qa.py':'reports/gui-configuration-evidence-2026-10-08/gui_snapshots_qa.py',
 'physical_reference_gui_qa.py':'reports/tracking-evidence-2026-10-08/physical_reference_gui_qa.py',
 'gui_snapshot_collection.txt':'reports/gui-configuration-evidence-2026-10-08/gui_snapshot_collection.txt',
}
record={'date':'2026-10-09','source_revision':subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),'method':'Inventory of exact repository .tmp tree; preserve unique historical QA/collection methods, remove generated test trees and obsolete one-shot amendment scripts/tools. Git history remains untouched.','removed_files':len(files),'removed_bytes':sum(p.stat().st_size for p in files),'preserved':[],'duplicate_junit':['.tmp/gui-snapshots-final-focused-01.xml matches reports/gui-configuration-evidence-2026-10-08/snapshot-tests.xml','.tmp/gui-snapshots-suite-03.xml matches reports/gui-configuration-evidence-2026-10-08/initial-gui-tests.xml'],'disposable_categories':['pytest basetemp fixture trees (including synthetic credentials/output examples)','copied ffmpeg.exe/ffprobe.exe diagnostic tools','superseded one-shot doc amendment/report/check scripts','duplicate JUnit reports'],'limits':'No actual runtime recovery, operator history, firmware, native source, environment/dependency or dated rig evidence deleted. Moved QA scripts retain their historical method/platform assumptions; no rerender claimed.'}
for name,destination in retained.items():
 src=scratch/name;dest=root/destination
 assert not dest.exists()
 digest=hashlib.sha256(src.read_bytes()).hexdigest();shutil.copyfile(src,dest)
 record['preserved'].append({'original':'.tmp/'+name,'destination':destination,'sha256':digest})
base=root/'reports/review-evidence-2026-10-09';(base/'cleanup.json').write_text(json.dumps(record,indent=2)+'\n')
shutil.rmtree(scratch)
print(json.dumps({'removed_files':record['removed_files'],'removed_bytes':record['removed_bytes'],'preserved_artifacts':len(retained)}))
