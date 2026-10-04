from PyQt6.QtCore import QSettings, QTimer
from PyQt6.QtWidgets import QApplication
from cephvr.gui.layouts import fit_window_to_screen
from cephvr.gui.review import ReviewControls
from cephvr.gui.theme import apply_theme
from cephvr.gui.window import DashboardWindow
app = QApplication([])
apply_theme(app)
window = DashboardWindow(sample=True, settings=QSettings('/private/tmp/cephvr-cards.ini', QSettings.Format.IniFormat))
controls = ReviewControls(window)
fit_window_to_screen(window)
window.page_buttons[1].click()
window.show()
def capture():
    window.protocol.editor.select_node(1)
    window.grab().save('reports/gui-dashboard-2026-10-01/protocol-cards-wide.png')
    window.resize(720,800)
    QTimer.singleShot(300, narrow)
def narrow():
    window.grab().save('reports/gui-dashboard-2026-10-01/protocol-cards-narrow.png')
    print('Captured', flush=True)
    app.quit()
QTimer.singleShot(600,capture)
app.exec()
