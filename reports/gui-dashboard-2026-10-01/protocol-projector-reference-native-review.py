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
composer.add_file('Texture', str(assets / 'light.png'), 'Front')
composer.add_file('Looming image', str(assets / 'dark.png'), 'Left')
composer.add_file('Image', str(assets / 'light.png'), 'Right')
window.show()
window.raise_()
window.activateWindow()
root = Path('reports/gui-dashboard-2026-10-01')
def capture():
    scroll.verticalScrollBar().setValue(composer.mapTo(scroll.widget(), QPoint(0, 0)).y() - 115)
    QTimer.singleShot(350, wide)
def wide():
    window.grab().save(str(root / 'protocol-projector-reference.png'))
    window.resize(720, 800)
    QTimer.singleShot(350, narrow)
def narrow():
    scroll.ensureWidgetVisible(composer.rows['Left'], 0, 0)
    QTimer.singleShot(350, finish)
def finish():
    window.grab().save(str(root / 'protocol-projector-reference-narrow.png'))
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
