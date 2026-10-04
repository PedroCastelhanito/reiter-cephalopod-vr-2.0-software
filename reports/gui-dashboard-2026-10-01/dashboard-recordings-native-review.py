import sys
from pathlib import Path
from PyQt6.QtCore import QSettings, QTimer
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
window.page_buttons[0].click()
window.show()
window.raise_()
window.activateWindow()
root = Path('reports/gui-dashboard-2026-10-01')
def protocol():
    window.grab().save(str(root / 'dashboard-recordings.png'))
    window.resize(720, 800)
    QTimer.singleShot(350, narrow)
def narrow():
    window.dashboard.config_scroll.ensureWidgetVisible(window.recordings)
    QTimer.singleShot(350, capture_narrow)
def capture_narrow():
    window.grab().save(str(root / 'dashboard-recordings-narrow.png'))
    window.resize(1175, 883)
    fit_window_to_screen(window)
    window.page_buttons[1].click()
    QTimer.singleShot(350, protocol_page)
def protocol_page():
    window.grab().save(str(root / 'protocol-without-recordings.png'))
    print('Native captures complete; inspection closed.', flush=True)
    window.close()
    app.quit()
if '--capture' in sys.argv:
    QTimer.singleShot(500, protocol)
else:
    QTimer.singleShot(500, lambda: print(f'Visible: {window.isVisible()}', flush=True))
app.exec()
