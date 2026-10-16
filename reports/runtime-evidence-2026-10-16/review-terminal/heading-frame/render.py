"""Offscreen compact caption geometry and shared page-heading CRT evidence."""
import json
from pathlib import Path
from PyQt6.QtCore import QPoint, QRect
from PyQt6.QtWidgets import QApplication
from cephvr.gui.appearance import ReviewAppearance
from cephvr.gui.review import ReviewControls
from cephvr.gui.theme import apply_theme
from cephvr.gui.window import DashboardWindow

app=QApplication([])
apply_theme(app)
window=DashboardWindow(sample=True, device_review=True)
controls=ReviewControls(window, simulate_projectors=True)
appearance=ReviewAppearance(window, window.dashboard, window.page_header, None)
appearance.select('retro_console')
window.show()
root=Path(__file__).parent
results={}
for width in (1440,1175,720):
 window.resize(width,940)
 window.page_buttons[2].click()
 window.devices.tabs.setCurrentIndex(2)
 window.devices.projectors.setup_tabs.setCurrentIndex(2)
 for _ in range(6): app.processEvents()
 timing=window.devices.projectors.timing
 results[str(width)]={'card_width':timing.width(),'caption_width':timing.caption.width(),'caption_hint':timing.caption.sizeHint().width()}
 assert timing.caption.width() == timing.caption.sizeHint().width()
 assert timing.caption.width() < timing.width()/2
 timing.grab().save(str(root/f'photodiode-{width}.png'))
for index,button in enumerate(window.page_buttons):
 button.click()
 app.processEvents()
 assert window.page_title.graphicsEffect() is not None
 window.grab().copy(QRect(window.page_header.mapTo(window, QPoint()), window.page_header.size())).save(str(root/f'heading-{index}.png'))
appearance.crt_action.setChecked(False)
assert window.page_title.graphicsEffect() is None
window.grab().copy(QRect(window.page_header.mapTo(window, QPoint()), window.page_header.size())).save(str(root/'heading-no-glow.png'))
appearance.select('standard')
assert window.page_title.graphicsEffect() is None
(root/'geometry.json').write_text(json.dumps(results,indent=2)+'\n')
window.close()
