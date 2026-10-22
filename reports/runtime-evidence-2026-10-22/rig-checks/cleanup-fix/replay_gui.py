import json,re,subprocess,sys
from pathlib import Path
out=Path('reports/runtime-evidence-2026-10-22/rig-checks/cleanup-fix')
s=(out/'gui-full.log').read_text(encoding='utf-8-sig',errors='replace')
nodes=list(dict.fromkeys(node.strip() for node in re.findall(r'\] FAILED (tests/[^\r\n]+)',s)))
(out/'gui-failed-nodeids.json').write_text(json.dumps(nodes,indent=2),encoding='utf-8')
print(nodes,flush=True)
command=[sys.executable,'-u','-X','faulthandler','-m','pytest','-p','slot_exception_checks','-vv','--timeout=60','--junitxml='+str(out/'gui-serial-replays.xml'),*nodes]
with (out/'gui-serial-replays.log').open('w',encoding='utf-8') as stream:
 result=subprocess.run(command,stdout=stream,stderr=subprocess.STDOUT)
print('serial pytest exit',result.returncode,flush=True)
print((out/'gui-serial-replays.log').read_text(encoding='utf-8')[-14000:])
sys.exit(result.returncode)
