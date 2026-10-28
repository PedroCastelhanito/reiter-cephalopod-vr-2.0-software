"""Compare the final tank-face raster against one unfolded physical field."""

import json
import math
from pathlib import Path

import numpy as np
from PyQt6.QtCore import QPointF
from PyQt6.QtGui import QImage, QPainter, QPolygonF
from PyQt6.QtWidgets import QApplication

from cephvr.gui.projector_geometry import RigDimensions
from cephvr.gui.trial_preview_canvas import PreviewCanvas
from cephvr.gui.trial_preview_media import PreviewMedia
from cephvr.gui.trial_preview_plan import PreviewPlan
from cephvr.gui.trial_preview_rig import PreviewRig
from cephvr.gui.trial_preview_surfaces import PreviewGeometry
from cephvr.visual_stimulus.config.grating_field import SurfaceUnfolder
from cephvr.visual_stimulus.config.models.program_model import Program
from cephvr.visual_stimulus.rendering.color import linear_to_srgb

protocol = Path('C:/Users/ReiterU_PC/Desktop/Alsu/protocols/gratings_protocol.json')
calibration = Path('C:/Users/ReiterU_PC/Desktop/Pedro/configs/projectors_config.json')
payload = json.loads(protocol.read_text())
data = payload['trials'][0]['program']
epoch = data['sequence'][0]['body'][0]
for s in epoch['settings']:
    s['pattern']['feature_sharpness'] = 0.0
    s['pattern']['frequency']['value'] = .05
program = Program.model_validate_json(json.dumps(data))
values = json.loads(calibration.read_text())['values']
rig = RigDimensions(*(values['rig.'+k] for k in ('width','depth','height')), tuple(values['rig.subject_'+k] for k in 'xyz'))
faces = ('Front','Left','Right','Bottom')
drafts = {face:{k.rsplit('.',1)[-1]:str(v) for k,v in values.items() if k.startswith('screens.'+face+'.')} for face in faces}
resolutions = {face:(int(values[f'screens.{face}.reference_width_px']),int(values[f'screens.{face}.reference_height_px'])) for face in faces}
geometry = PreviewGeometry.from_drafts(rig, drafts, resolutions)
artifact = geometry.artifact()
app = QApplication([])
media = PreviewMedia(program, '', None)
plan = PreviewPlan(program, artifact.display.geometry)
layers = plan.seek(0)
canvases = {face:PreviewCanvas(face,media,geometry) for face in faces}
view = PreviewRig(geometry, canvases)
for face,canvas in canvases.items():
    canvas.present(layers,0,(0,0,0))
    view.frames[face]=canvas.frame_image()
source = next(s for s in layers if s.setting.linked_to is None)
a=math.radians(source.values['rotation'])
unfolder=SurfaceUnfolder(artifact.display.geometry)
for face in faces:
    image=QImage(1024,1024,QImage.Format.Format_RGB32)
    image.fill(0)
    painter=QPainter(image)
    view.draw_screen(painter,face,QPolygonF([QPointF(0,1024),QPointF(1024,1024),QPointF(1024,0),QPointF(0,0)]))
    painter.end()
    surface=geometry.surfaces[face]
    corners=surface.corners
    w,h=math.dist(corners[0],corners[1]),math.dist(corners[0],corners[3])
    errors=[]
    for x in range(90,950,43):
        for y in range(90,950,43):
            q=unfolder.point(face.lower(),((x+.5)/1024-.5)*w,(.5-(y+.5)/1024)*h)
            phase=source.values['frequency']*(q[0]*math.cos(a)+q[1]*math.sin(a))
            expected=linear_to_srgb(.5+.5*math.cos(2*math.pi*phase))
            errors.append(abs(image.pixelColor(x,y).redF()-expected))
    print(face, 'mean_error',round(float(np.mean(errors)),4),'max_error',round(max(errors),4),flush=True)
    image.save(str(Path(__file__).with_name('final-'+face+'.png')))
