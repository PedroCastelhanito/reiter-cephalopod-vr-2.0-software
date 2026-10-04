import sys
from pathlib import Path
from PyQt6.QtCore import QSettings, QTimer, Qt
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
window.protocol.editor.timeline.choose(1, Qt.KeyboardModifier.NoModifier)
window.show()
window.raise_()
window.activateWindow()
root = Path('reports/gui-dashboard-2026-10-01')
def protocol():
    window.grab().save(str(root / 'protocol-inline-batch-edit.png'))
    window.protocol.editor.modes.setCurrentIndex(0)
    QTimer.singleShot(350, create)
def create():
    window.grab().save(str(root / 'protocol-inline-batch-create.png'))
    window.protocol.editor.modes.setCurrentIndex(1)
    window.resize(720, 800)
    QTimer.singleShot(350, narrow)
def narrow():
    window.grab().save(str(root / 'protocol-inline-batch-narrow.png'))
    print('Native captures complete; inspection closed.', flush=True)
    window.close()
    app.quit()
if '--capture' in sys.argv:
    QTimer.singleShot(500, protocol)
else:
    QTimer.singleShot(500, lambda: print(f'Visible: {window.isVisible()}', flush=True))
app.exec()
