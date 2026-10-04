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
editor.select_projector(0, 'Left', -1)
editor.add_file('Looming image', str(root / 'example.png'))
editor.select_projector(0, 'Right', -1)
editor.remove_stimulus()
editor.add_file('Image', str(root / 'example.png'))
editor.select_projector(0, 'Left', -1)
window.show()
def capture():
    window.grab().save('reports/gui-dashboard-2026-10-01/protocol-compact-stimulus-overview.png')
    node = editor.program.sequence[0]
    looming = next(i for i, value in enumerate(node.settings) if value.kind == 'image' and value.width.kind == 'keyframes')
    editor.select_projector(0, 'Left', looming)
    QTimer.singleShot(300, capture_loom)
def capture_loom():
    window.grab().save('reports/gui-dashboard-2026-10-01/protocol-compact-stimulus-looming.png')
    editor.parameters.more.setChecked(True)
    QTimer.singleShot(300, capture_more)
def capture_more():
    window.protocol.config_scroll.ensureWidgetVisible(editor.parameters)
    window.grab().save('reports/gui-dashboard-2026-10-01/protocol-compact-stimulus-more.png')
    editor.parameters.more.setChecked(False)
    window.resize(720,800)
    QTimer.singleShot(300, capture_narrow)
def capture_narrow():
    window.protocol.config_scroll.ensureWidgetVisible(editor.parameters)
    QTimer.singleShot(300, done)
def done():
    window.grab().save('reports/gui-dashboard-2026-10-01/protocol-compact-stimulus-narrow.png')
    print('Compact stimulus captures complete', flush=True)
    app.quit()
QTimer.singleShot(600, capture)
app.exec()
