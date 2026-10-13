"""Real wrong-adapter context rejection and exact release; no recording/cameras."""
import os
from pathlib import Path
_handles = [os.add_dll_directory(str(Path('C:/Users/ReiterU_PC/miniforge3/envs/CephVR') / suffix)) for suffix in ('', 'DLLs', 'Library/bin')]
import dataclasses
import json
import sys
from cephvr.visual_stimulus.config.models.display_profile import DisplayProfile
from cephvr.visual_stimulus.rendering.native import ModernGLPort
from cephvr.visual_stimulus.rendering.native_display import DisplayGpuUnavailableError

root = Path.cwd()
config = json.loads((root/'config/last_configuration.json').read_text())['configuration']
visual = next(b['visual_stimulus'] for b in config['backends'] if 'visual_stimulus' in b)
display = DisplayProfile.model_validate_json(visual['display']['profile_json'])
records = []
for cycle in range(3):
    announced=[]
    port=ModernGLPort(root,announce=lambda key,path: announced.append(key))
    try:
        port.initialize_display(display)
    except DisplayGpuUnavailableError as error:
        receipt=port.release()
        assert not receipt.outstanding
        assert 'visual_stimulus:glfw' in receipt.released
        assert not port._outputs and not port._orphan_windows
        records.append({'cycle':cycle,'error':str(error),'remedy':error.remedy,'announced':announced,'release':dataclasses.asdict(receipt)})
    else:
        port.release()
        raise AssertionError('isolated executable unexpectedly has a configured GPU preference')
result={'method':'isolated identical executable without GPU preference; actual ModernGLPort/context cleanup', 'executable':sys.executable,'records':records}
Path(__file__).with_suffix('.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
print(json.dumps(result,indent=2))
