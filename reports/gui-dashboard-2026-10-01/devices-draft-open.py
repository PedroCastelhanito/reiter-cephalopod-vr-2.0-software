"""Open the reviewed Devices draft without launching hardware."""

from PyQt6.QtCore import QSettings
from PyQt6.QtWidgets import QApplication

from cephvr.gui.layouts import fit_window_to_screen
from cephvr.gui.review import ReviewControls
from cephvr.gui.theme import apply_theme
from cephvr.gui.window import DashboardWindow

app = QApplication([])
app.setApplicationName("CephVR2.0 Dashboard")
apply_theme(app)
window = DashboardWindow(sample=True, settings=QSettings("CephVR", "Frontend"))
controls = ReviewControls(window)
fit_window_to_screen(window)
window.page_buttons[1].click()
window.show()
window.raise_()
window.activateWindow()
app.exec()
