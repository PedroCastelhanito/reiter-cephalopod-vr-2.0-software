import json
from pathlib import Path
from PyQt6.QtGui import QImage, QColor
from cephvr.gui.protocol_document import blank_program
from PyQt6.QtCore import QSettings, QTimer, QRect
from PyQt6.QtWidgets import QApplication
from cephvr.gui.layouts import fit_window_to_screen
from cephvr.gui.review import ReviewControls
from cephvr.gui.theme import apply_theme
from cephvr.gui.window import DashboardWindow
app = QApplication([])
apply_theme(app)
window = DashboardWindow(sample=True, settings=QSettings('/private/tmp/cephvr-parameters.ini', QSettings.Format.IniFormat))
controls = ReviewControls(window)
fit_window_to_screen(window)
window.page_buttons[1].click()
p = window.devices.projectors
p.keys = ['review-left', 'review-right']
p.assignments = {'review-left':'Left', 'review-right':'Right'}
p.diagram.outputs = [('2', QRect(0,0,1920,1080)), ('3', QRect(1920,0,1920,1080))]
p.update_participation()
root = Path('/private/tmp/cephvr-file-review-assets')
root.mkdir(exist_ok=True)
image = QImage(32,32,QImage.Format.Format_RGB32)
image.fill(QColor('gray'))
image.save(str(root / 'example.png'))
(root / 'example.texture.json').write_text(json.dumps({'cephvr_asset_type':'texture_design','kind':'texture','pattern':'grating','params':{'tile_width_mm':104},'preview_file':'example.png'}))
window.protocol.assets.folders['root'].editor.setText(str(root))
window.protocol.editor.set_program(blank_program())
window.protocol.editor.add_file('Texture', str(root / 'example.texture.json'))
editor = window.protocol.editor
editor.edit_epoch('add')
editor.add_file('Texture', str(root / 'example.texture.json'))
editor.select_node(0)
editor.parameters.tabs.setCurrentIndex(0)
window.show()
def capture():
    editor.open_group_dialog()
    dialog = editor.group_dialog
    dialog.first.setCurrentIndex(0)
    dialog.last.setCurrentIndex(1)
    dialog.repetitions.setText('3')
    dialog.add_variation()
    dialog.rows[0].values.setText('10, 20')
    QTimer.singleShot(400, lambda: capture_dialog(dialog))
def capture_dialog(dialog):
    dialog.grab().save('reports/gui-dashboard-2026-10-01/protocol-three-stages-group-dialog.png')
    dialog.apply()
    editor.group_editor.more.setChecked(True)
    QTimer.singleShot(300, group)
def group():
    window.grab().save('reports/gui-dashboard-2026-10-01/protocol-three-stages-group.png')
    editor.open_preview()
    QTimer.singleShot(300, preview)
def preview():
    editor.expanded_preview.grab().save('reports/gui-dashboard-2026-10-01/protocol-three-stages-expanded.png')
    editor.expanded_preview.close()
    print('Group authoring and expansion captured', flush=True)
    app.quit()
QTimer.singleShot(600, capture)
app.exec()
