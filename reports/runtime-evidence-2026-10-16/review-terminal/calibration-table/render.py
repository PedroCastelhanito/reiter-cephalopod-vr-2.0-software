"""Offscreen screen-calibration layout checks with simulated projector outputs."""
import json
from pathlib import Path
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
appearance.crt_action.setChecked(False)
window.show()
window.page_buttons[2].click()
window.devices.tabs.setCurrentIndex(2)
panel=window.devices.projectors
panel.setup_tabs.setCurrentIndex(0)
panel.measurements.fields['Front','reference_x_mm'].setText('30.4')
panel.measurements.fields['Front','reference_y_mm'].setText('90')
results={}
root=Path(__file__).parent
for width in (1440,1175,720):
 window.resize(width,940)
 for _ in range(8): app.processEvents()
 measurements=panel.measurements.table
 header=measurements.horizontalHeader()
 results[width]={'table_width': measurements.width(), 'columns':[header.sectionSize(i) for i in range(3)], 'measured_header_lines':header.label_layout(1,header.sectionSize(1)).lineCount(), 'scale':panel.measurements.scales['Front'].text()}
 panel.measurements.grab().save(str(root/f'measurements-{width}.png'))
 panel.calibration.grab().save(str(root/f'offsets-{width}.png'))
(root/'geometry.json').write_text(json.dumps(results,indent=2)+'\n')
print(json.dumps(results))
window.close()
