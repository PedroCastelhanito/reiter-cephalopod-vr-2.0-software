"""Offscreen shared HUD style/section/cross-tab appearance evidence."""
import json
from pathlib import Path
from PyQt6.QtCore import QEvent
from PyQt6.QtWidgets import QApplication
from cephvr.gui.appearance import ReviewAppearance
from cephvr.gui.components import StatusColumn
from cephvr.gui.theme import apply_theme
from cephvr.gui.window import DashboardWindow
app=QApplication([])
apply_theme(app)
window=DashboardWindow(sample=True,device_review=True)
appearance=ReviewAppearance(window,window.dashboard,window.page_header,None)
window.show()
root=Path(__file__).parent
records=[]
for style in ('retro_console','standard','retro_console'):
 appearance.select(style)
 for width in (1440,720):
  window.resize(width,940)
  for page in (0,2,3):
   window.page_buttons[page].click()
   panels=range(4) if page==2 else (0,)
   for panel in panels:
    if page==2: window.devices.tabs.setCurrentIndex(panel)
    for _ in range(5): app.processEvents()
    status=window.dashboard.status_column if page==0 else window.tracking.status if page==3 else window.devices.panels[panel].status_column
    assert isinstance(status,StatusColumn)
    name=f'{page}-{panel}-{width}-{style}'
    status.hud_card.grab().save(str(root/f'{name}.png'))
    records.append(dict(name=name,text=status.hud.toPlainText(),rows=status.rows))
(root/'rows.json').write_text(json.dumps(records,indent=2)+'\n')
appearance.select('standard')
window.close()
window.deleteLater()
app.sendPostedEvents(None,QEvent.Type.DeferredDelete)
app.processEvents()
