"""Owner-authorized actual managed-image OpenGL and CUDA identity check."""
import os
from pathlib import Path
import dataclasses
import json
import sys

_dll_handles = [os.add_dll_directory(str(Path('C:/Users/ReiterU_PC/miniforge3/envs/CephVR') / suffix)) for suffix in ('', 'DLLs', 'Library/bin')]
from cephvr.platform.windows.nvidia_device import _enumerate_cuda_devices
from cephvr.visual_stimulus.config.models.display_profile import DisplayProfile
from cephvr.visual_stimulus.rendering.native import ModernGLPort

config = json.loads(Path('config/last_configuration.json').read_text(encoding='utf-8'))['configuration']
visual = next(b['visual_stimulus'] for b in config['backends'] if 'visual_stimulus' in b)
display = DisplayProfile.model_validate_json(visual['display']['profile_json'])
result = {'scope':'actual managed executable; bounded output initialization/Idle and release; no camera/recording', 'executable':sys.executable, 'cuda_devices':[dataclasses.asdict(d) for d in _enumerate_cuda_devices()], 'contexts':[]}
port = ModernGLPort(Path.cwd(), announce=lambda *_: None)
verify = port._verify_render_gpu
def record(renderer, vendor):
    entry = {'renderer':renderer,'vendor':vendor}
    result['contexts'].append(entry)
    entry['verified_identity'] = verify(renderer,vendor)
    return entry['verified_identity']
port.gpu_identity_provider = record
try:
    initialized = port.initialize_display(display)
    result['initialization'] = dataclasses.asdict(initialized)
    result['render_pass'] = len(result['contexts']) == len(display.active_outputs)
except Exception as error:
    result['render_pass'] = False
    result['error'] = str(error)
finally:
    receipt = port.release()
    result['release'] = dataclasses.asdict(receipt)
    assert not receipt.outstanding, receipt
Path(__file__).with_suffix('.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
print(json.dumps(result,indent=2),flush=True)
if not result['render_pass']:
    raise SystemExit(1)
