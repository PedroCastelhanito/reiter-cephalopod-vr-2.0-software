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
from cephvr.gui.protocol_nodes import edit_epoch
from cephvr.gui.epoch_batch import apply_batch, LayerTarget, epoch_paths
program=editor.program
for i in range(3):
    program,_=edit_epoch(program,i,"duplicate")
program=apply_batch(program,((1,),),LayerTarget("Left","Texture"),{"Speed":"15"})
editor.set_program(program)
editor.select_epochs(((0,),(1,),(2,)))
panel=editor.batch_edit
panel.face.setCurrentIndex(panel.face.findData("Left"))
panel.layer.setCurrentIndex(next(i for i,t in enumerate(panel.targets) if t.family=="Texture"))
create=editor.create_batch
create.composer.program=program.model_copy(update={"sequence":(program.sequence[0],)})
create.composer.duration.setText("10")
create.composer.refresh_layers()
create.vary.setChecked(True)
create.add_variation()
create.rows[0].values.setText("10, 20, 40")
create.repetitions.setText("2")
create.refresh_preview()
def capture():
    window.protocol.config_scroll.ensureWidgetVisible(panel)
    QTimer.singleShot(300, edit_capture)
def edit_capture():
    window.grab().save("reports/gui-dashboard-2026-10-01/protocol-batch-edit.png")
    editor.modes.setCurrentIndex(0)
    window.protocol.config_scroll.ensureWidgetVisible(create)
    QTimer.singleShot(300, create_capture)
def create_capture():
    window.grab().save("reports/gui-dashboard-2026-10-01/protocol-batch-create.png")
    window.protocol.config_scroll.ensureWidgetVisible(create.add_button)
    QTimer.singleShot(300, create_footer)
def create_footer():
    window.grab().save("reports/gui-dashboard-2026-10-01/protocol-batch-create-options.png")
    window.resize(720,800)
    editor.modes.setCurrentIndex(1)
    window.protocol.config_scroll.ensureWidgetVisible(panel)
    QTimer.singleShot(300, narrow_capture)
def narrow_capture():
    window.protocol.config_scroll.ensureWidgetVisible(panel)
    QTimer.singleShot(300, done)
def done():
    window.grab().save("reports/gui-dashboard-2026-10-01/protocol-batch-narrow.png")
    print("Batch planner captures complete",flush=True)
    app.quit()
QTimer.singleShot(600,capture)
app.exec()
