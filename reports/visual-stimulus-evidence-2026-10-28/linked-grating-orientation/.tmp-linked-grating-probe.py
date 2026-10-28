import json
import math
from PyQt6.QtWidgets import QApplication
from cephvr.gui.trial_preview_canvas import PreviewCanvas
from cephvr.gui.trial_preview_media import PreviewMedia
from cephvr.gui.projector_geometry import RigDimensions
from cephvr.gui.protocol_document import blank_program
from cephvr.gui.stimulus_presets import add_stimulus
from cephvr.gui.rig_parameter_edits import patch_setting
from cephvr.gui.trial_preview_plan import PreviewPlan
from cephvr.gui.trial_preview_surfaces import PreviewGeometry
from cephvr.visual_stimulus.config.models.program_model import Program

program = blank_program()
for face in ('Bottom', 'Front', 'Left', 'Right'):
    program = add_stimulus(program, 0, 'Grating', (face,))
data = program.model_dump(mode='json')
settings = data['sequence'][0]['settings']
patch_setting(settings[0], {'Orientation': '180', 'Speed': '20'})
for target in settings[1:]:
    target['linked_to'] = settings[0]['instance_id']
    target['motion'] = {k: {'kind':'hold'} for k in ('x','y','rotation')}
from pathlib import Path
payload = json.loads(Path('C:/Users/ReiterU_PC/Desktop/Alsu/protocols/gratings_protocol.json').read_text())
program = Program.model_validate_json(json.dumps(payload['trials'][0]['program']))
calibration = json.loads(Path('C:/Users/ReiterU_PC/Desktop/Pedro/configs/projectors_config.json').read_text())['values']
rig = RigDimensions(*(calibration['rig.'+k] for k in ('width','depth','height')), tuple(calibration['rig.subject_'+k] for k in 'xyz'))
drafts = {face: {k.rsplit('.',1)[-1]: str(v) for k,v in calibration.items() if k.startswith('screens.'+face+'.')} for face in ('Bottom','Front','Left','Right')}
resolutions = {face: ((720,1280) if face == 'Bottom' else (1280,720)) for face in drafts}
preview_geometry = PreviewGeometry.from_drafts(rig, drafts, resolutions)
geometry = preview_geometry.artifact().display.geometry
plan = PreviewPlan(program, geometry)
app = QApplication([])
media = PreviewMedia(program, '', None)
for t in (0, 25000000):
    print('time', t)
    for layer in plan.seek(t):
        print(layer.setting.space.mappings[0].surface_id, {k:round(layer.values[k],6) for k in ('rotation','phase_x','x','y','frequency')})
        face = layer.setting.space.mappings[0].surface_id.title()
        canvas = PreviewCanvas(face, media, preview_geometry)
        canvas.present((layer,), t, (0,0,0))
        canvas.frame_image().save(f'.tmp-grating-{face}-{t}.png')
