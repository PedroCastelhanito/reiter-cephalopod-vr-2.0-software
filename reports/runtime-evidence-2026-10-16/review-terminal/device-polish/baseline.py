from pathlib import Path
import json
from PyQt6.QtCore import QPoint
from PyQt6.QtWidgets import QApplication
from cephvr.gui.appearance import ReviewAppearance
from cephvr.gui.review import ReviewControls
from cephvr.gui.theme import apply_theme
from cephvr.gui.window import DashboardWindow
app=QApplication([]); apply_theme(app)
w=DashboardWindow(sample=True,device_review=True); controls=ReviewControls(w,simulate_projectors=True)
a=ReviewAppearance(w,w.dashboard,w.page_header,None); a.select('retro_console')
w.page_buttons[2].click(); w.show(); root=Path(__file__).parent; data={}
for width in (1440,1175,720):
 w.resize(width,940)
 for _ in range(5): app.processEvents()
 camera=w.devices.cameras
 editors=[camera.trigger_source,camera.fields['trigger_frequency_hz'],camera.trigger_pin]
 data[width]=[dict(y=e.mapTo(camera.configuration,QPoint()).y(),height=e.height(),width=e.width()) for e in editors]
 camera.configuration.grab().save(str(root/f'camera-alignment-{width}.png'))
(root/'camera-alignment.json').write_text(json.dumps(data,indent=2))
w.hide();w.deleteLater();app.processEvents()
print(data)
