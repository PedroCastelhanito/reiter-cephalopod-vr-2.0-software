"""Offscreen device-page captures with isolated fixtures and settings."""
from pathlib import Path
from PyQt6.QtCore import QCoreApplication, QEvent, QSettings
from PyQt6.QtWidgets import QApplication
from cephvr.gui.review import ReviewControls
from cephvr.gui.theme import apply_theme
from cephvr.gui.window import DashboardWindow

app = QApplication([])
apply_theme(app)
window = DashboardWindow(sample=True, settings=QSettings('/tmp/cephvr-devices-review.ini', QSettings.Format.IniFormat))
controls = ReviewControls(window, simulate_projectors=True)
window.page_buttons[2].click()
for width in (1280, 720):
    window.resize(width, 940)
    window.show()
    for index, name in enumerate(('cameras', 'microcontroller', 'projectors', 'spikeglx')):
        window.devices.tabs.setCurrentIndex(index)
        for _ in range(4):
            app.processEvents()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        app.processEvents()
        window.grab().save(str(Path(__file__).parent / f'{name}-{width}.png'))
window.tracking.annotation.close()
window.hide()
window.deleteLater()
QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
app.processEvents()
