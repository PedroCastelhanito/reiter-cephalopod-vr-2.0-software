"""Offscreen camera HUD review; sample inventory, no backend rate invented."""
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
appearance.select('retro_console')
window.show()
window.page_buttons[2].click()
window.devices.tabs.setCurrentIndex(0)
panel=window.devices.cameras
root=Path(__file__).parent
for width in (1440,720):
 window.resize(width,940)
 for _ in range(5): app.processEvents()
 panel.status_column.hud_card.grab().save(str(root/f'hud-{width}.png'))
(root/'hud.txt').write_text(panel.status_column.hud.toPlainText()+'\n')
appearance.select('standard')
window.close()
window.deleteLater()
app.sendPostedEvents(None,QEvent.Type.DeferredDelete)
app.processEvents()
