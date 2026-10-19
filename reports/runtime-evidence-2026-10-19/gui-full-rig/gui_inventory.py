"""Offscreen fixture inventory/renders; no native UI or device acceptance."""
import csv
import json
from pathlib import Path

from PyQt6.QtGui import QAction
from cephvr.gui.camera_inventory import CameraDraft
from PyQt6.QtWidgets import (
    QAbstractButton, QAbstractSpinBox, QApplication, QComboBox, QLineEdit,
    QTabBar, QWidget,
)
from cephvr.gui.theme import apply_theme
from cephvr.gui.view import Phase, review_view
from cephvr.gui.window import DashboardWindow

OUT = Path(__file__).resolve().parent
app = QApplication([])
apply_theme(app)
window = DashboardWindow(sample=True, device_review=True)
window.apply_view(review_view(Phase.CONFIGURATION))
window.show()
rows = []
errors = []
try:
    data = json.loads((OUT / 'before-runtime_gui.json').read_text())
    cameras = window.devices.cameras
    cameras.drafts = [CameraDraft('camera-' + c['serial'], c['role'], c['serial'], 'Saved rig identity (fixture)', enabled=c['enabled']) for c in data['experiment']['cameras']]
    cameras.populate_inventory()
    cameras.load_selected()
    cameras.drafts_changed.emit()
    window.snapshots.restore(window.snapshots.validate(data))
except Exception as exc:
    errors.append({'saved_fixture_restore': repr(exc)})

for style in ('standard', 'retro_console'):
    window.appearance.select(style, persist=False)
    for width, height in ((1440, 940), (800, 800)):
        window.resize(width, height)
        for page in range(4):
            window.page_buttons[page].setChecked(True)
            window.select_page(page)
            sections = ([(0, None), (1, None), *[(2, sub) for sub in range(window.devices.projectors.setup_tabs.count())], (3, None)] if page == 2 else [(sub, None) for sub in range(4)] if page == 3 else [(0, None)])
            for section, subsection in sections:
                if page == 2:
                    window.devices.tab_bar.setCurrentIndex(section)
                    if subsection is not None:
                        window.devices.projectors.setup_tabs.setCurrentIndex(subsection)
                elif page == 3:
                    window.tracking.tabs.setCurrentIndex(section)
                for _ in range(4):
                    app.processEvents()
                stem = f'{style}-{width}-page{page}-section{section}' + (f'-sub{subsection}' if subsection is not None else '')
                window.grab().save(str(OUT / (stem + '.png')))
                root = window.stack.currentWidget()
                for control in root.findChildren(QWidget):
                    if not isinstance(control, (QAbstractButton, QLineEdit, QComboBox, QAbstractSpinBox, QTabBar)):
                        continue
                    caption = control.accessibleName()
                    if not caption and isinstance(control, QAbstractButton):
                        caption = control.text()
                    if not caption and isinstance(control, QLineEdit):
                        caption = control.placeholderText()
                    if not caption and isinstance(control, QComboBox):
                        caption = control.currentText()
                    rows.append({
                        'fixture': stem, 'class': type(control).__name__,
                        'name': caption, 'object_name': control.objectName(),
                        'visible': control.isVisible(), 'enabled': control.isEnabled(),
                        'width': control.width(), 'height': control.height(),
                        'tooltip': control.toolTip(),
                        'native_coverage': 'Unavailable: sky capture stalled; no native input issued',
                        'fixture_coverage': 'Constructed/rendered; owning GUI suite is separate behavioral evidence',
                    })

actions = [{'text': a.text(), 'enabled': a.isEnabled(), 'visible': a.isVisible(), 'checked': a.isChecked(), 'tooltip': a.toolTip(), 'native_coverage': 'Unavailable'} for a in window.findChildren(QAction)]
(OUT / 'menu-actions.json').write_text(json.dumps(actions, indent=2))
with (OUT / 'control-matrix.csv').open('w', newline='', encoding='utf-8') as stream:
    writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
    writer.writeheader()
    writer.writerows(rows)
(OUT / 'gui-inventory.json').write_text(json.dumps({
    'scope': 'Offscreen sample fixture, no connected devices, not physical per-control acceptance',
    'rows': len(rows), 'errors': errors,
    'rendered_states': sorted({r['fixture'] for r in rows}),
}, indent=2))
window.hide()
print(json.dumps({'control_rows': len(rows), 'restore_errors': errors}))
