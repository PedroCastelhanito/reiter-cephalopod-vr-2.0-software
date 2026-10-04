"""Native GUI review captures; no backend or hardware operations."""
from pathlib import Path
from PyQt6.QtCore import QSettings, QTimer
from PyQt6.QtWidgets import QApplication
from PyQt6.QtTest import QTest
from cephvr.gui.layouts import fit_window_to_screen
from cephvr.gui.review import ReviewControls
from cephvr.gui.theme import apply_theme
from cephvr.gui.window import DashboardWindow

app = QApplication([])
apply_theme(app)
window = DashboardWindow(sample=True, settings=QSettings('/private/tmp/cephvr-protocol.ini', QSettings.Format.IniFormat))
review = ReviewControls(window)
fit_window_to_screen(window)
window.show()
window.raise_()
window.activateWindow()
evidence = Path(__file__).parent

def capture():
    for index, name in ((0, 'dashboard'), (1, 'protocol'), (3, 'assets')):
        window.page_buttons[index].click()
        QTest.qWait(150)
        assert window.grab().save(str(evidence / f'protocol-{name}.png'))
    window.page_buttons[2].click()
    window.devices.tabs.setCurrentIndex(2)
    window.devices.projectors.setup_tabs.setCurrentIndex(2)
    window.devices.projectors.config_scroll.verticalScrollBar().setValue(9999)
    QTest.qWait(150)
    assert window.grab().save(str(evidence / 'protocol-rig.png'))
    window.resize(720, 800)
    window.page_buttons[1].click()
    QTest.qWait(150)
    assert window.grab().save(str(evidence / 'protocol-narrow.png'))
    print('Native captures saved; review window closed.', flush=True)
    window.close()
    app.quit()

QTimer.singleShot(300, capture)
app.exec()
