"""2026-10-04 native GUI evidence; local assets only, no backend connections."""
import sys
from pathlib import Path
from PyQt6.QtCore import QPoint, QSettings, QTimer
from PyQt6.QtGui import QImage
from PyQt6.QtWidgets import QApplication
from cephvr.gui.layouts import fit_window_to_screen
from cephvr.gui.review import ReviewControls
from cephvr.gui.theme import apply_theme
from cephvr.gui.window import DashboardWindow

app = QApplication([])
apply_theme(app)
window = DashboardWindow(sample=True, settings=QSettings('/private/tmp/cephvr-four-projectors.ini', QSettings.Format.IniFormat))
controls = ReviewControls(window, simulate_projectors=True)
fit_window_to_screen(window)
window.page_buttons[1].click()
window.protocol.editor.modes.setCurrentIndex(0)
assets = Path('/private/tmp/cephvr-projector-reference-assets')
assets.mkdir(exist_ok=True)
image = QImage(32, 32, QImage.Format.Format_RGB32)
image.fill(0)
image.save(str(assets / 'dark.png'))
image.fill(0xffffff)
image.save(str(assets / 'light.png'))
window.protocol.assets.folders['root'].editor.setText(str(assets))
composer = window.protocol.editor.create_batch.composer
composer.batch_label.setText('Adaptation')
composer.add_file('Texture', str(assets / 'light.png'), 'Front')
composer.add_file('Looming image', str(assets / 'dark.png'), 'Left')
composer.add_file('Image', str(assets / 'light.png'), 'Right')
composer.add_file('Looming image', str(assets / 'dark.png'), 'Front')
composer.rows['Front'].layer.setCurrentIndex(0)
editor = window.protocol.editor
program = editor.program
editor.set_program(program.model_copy(update={'sequence': tuple(e.model_copy(update={'batch_label': 'Baseline' if i != 1 else 'Flow'}) for i, e in enumerate(program.sequence))}))
editor.modes.setCurrentIndex(0)
window.show()
window.raise_()
window.activateWindow()
root = Path('reports/gui-dashboard-2026-10-01')
def capture():
    scroll.verticalScrollBar().setValue(composer.mapTo(scroll.widget(), QPoint(0, 0)).y() - 115)
    QTimer.singleShot(350, wide)
def wide():
    window.grab().save(str(root / 'protocol-layer-label.png'))
    composer.rows['Front'].layer.setCurrentIndex(1)
    QTimer.singleShot(350, layer_view)
def layer_view():
    window.grab().save(str(root / 'protocol-layer-label-selected.png'))
    composer.rows['Front'].layer.setCurrentIndex(0)
    batch = window.protocol.editor.create_batch
    batch.insert.setCurrentIndex(batch.insert.findData('label'))
    QTimer.singleShot(350, insertion)
def insertion():
    window.grab().save(str(root / 'protocol-layer-label-insertion.png'))
    window.protocol.editor.create_batch.insert.setCurrentIndex(0)
    row = composer.rows['Front']
    row.advanced.setChecked(True)
    for i in range(row.parameters.tabs.count()):
        if row.parameters.tabs.tabText(i) == 'Opacity':
            row.parameters.tabs.setCurrentIndex(i)
    QTimer.singleShot(350, advanced_view)
def advanced_view():
    scroll.ensureWidgetVisible(composer.rows['Front'].parameters, 0, 0)
    window.grab().save(str(root / 'protocol-layer-label-opacity.png'))
    composer.rows['Front'].advanced.setChecked(False)
    composer.mode.setCurrentIndex(1)
    arena = assets / 'arena.glb'
    arena.touch()
    params = composer.rows[''].parameters
    params.set_media_path(next(iter(params.asset_forms)), str(arena))
    QTimer.singleShot(350, arena_view)
def arena_view():
    window.page_buttons[1].click()
    app.processEvents()
    scroll.ensureWidgetVisible(composer.rows[""], 0, 0)
    window.grab().save(str(root / 'protocol-layer-label-arena.png'))
    composer.mode.setCurrentIndex(0)
    window.resize(720, 800)
    QTimer.singleShot(350, narrow)
def narrow():
    scroll.ensureWidgetVisible(composer.rows['Left'], 0, 0)
    QTimer.singleShot(350, finish)
def finish():
    window.grab().save(str(root / 'protocol-layer-label-narrow.png'))
    print('Native captures complete; inspection closed.', flush=True)
    window.close()
    app.quit()
from PyQt6.QtWidgets import QScrollArea
scroll = next(s for s in window.findChildren(QScrollArea) if s.isAncestorOf(composer))
if '--capture' in sys.argv:
    QTimer.singleShot(500, capture)
else:
    QTimer.singleShot(500, lambda: scroll.verticalScrollBar().setValue(composer.mapTo(scroll.widget(), QPoint(0, 0)).y() - 115))
    QTimer.singleShot(750, lambda: print(f'Visible: {window.isVisible()}', flush=True))
app.exec()
