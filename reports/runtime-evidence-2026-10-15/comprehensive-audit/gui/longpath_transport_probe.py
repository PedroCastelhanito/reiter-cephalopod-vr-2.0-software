import json
from pathlib import Path
from cephvr.platform.windows.paths import extended_path,logical_path
base=Path('C:/Users/ReiterU_PC/AppData/Local/Temp/cv-longpath-before-20261015')
markers=list(Path(extended_path(base)).glob('test_native_cancellation_handl0/*/20260929_experiment/.*.cleanup/.cephvr-reservation.json'))
assert len(markers)==1, len(markers)
marker=markers[0]
result={'synthetic_only':True,'logical_marker':logical_path(marker),'logical_chars':len(logical_path(marker)),'extended_bytes':len(marker.read_bytes())}
try:
    result['normal_bytes']=len(Path(logical_path(marker)).read_bytes())
except OSError as error:
    result['normal_error']={'type':type(error).__name__,'winerror':error.winerror}
Path('reports/runtime-evidence-2026-10-15/comprehensive-audit/gui/longpath-transport-probe.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
print(json.dumps(result))
