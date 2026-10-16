"""Offscreen SpikeGLX Use header fitting across widths and appearances."""
import json
from pathlib import Path
from PyQt6.QtCore import QEvent
from PyQt6.QtWidgets import QApplication
from cephvr.gui.appearance import ReviewAppearance
from cephvr.gui.theme import apply_theme
from cephvr.gui.window import DashboardWindow
app=QApplication([])
apply_theme(app)
window=DashboardWindow(sample=True,device_review=True)
appearance=ReviewAppearance(window,window.dashboard,window.page_header,None)
window.show()
window.page_buttons[2].click()
window.devices.tabs.setCurrentIndex(3)
window.devices.sync_inputs()
panel=window.devices.spikeglx
root=Path(__file__).parent
results=[]
for style in ('standard','retro_console'):
 appearance.select(style)
 for width in (1440,1175,720):
  window.resize(width,940)
  for _ in range(5): app.processEvents()
  header=panel.table.horizontalHeader()
  lines=header.label_layout(0,header.sectionSize(0)).lineCount()
  assert lines == 1
  results.append(dict(style=style,width=width,use_width=header.sectionSize(0),lines=lines))
  panel.mapping.grab().save(str(root/f'{style}-{width}.png'))
(root/'geometry.json').write_text(json.dumps(results,indent=2)+'\n')
appearance.select('standard')
window.close()
window.deleteLater()
app.sendPostedEvents(None,QEvent.Type.DeferredDelete)
app.processEvents()
