from pathlib import Path
import os

from PyQt6.QtCore import QTimer, QSettings
from PyQt6.QtWidgets import QApplication
from PyQt6.QtTest import QTest

from cephvr.gui.review import ReviewControls
from cephvr.gui.layouts import fit_window_to_screen
from cephvr.gui.theme import apply_theme
from cephvr.gui.window import DashboardWindow

evidence = Path('/Users/pedrocastelhanito/Dev/reiter-software/reiter-cephalopod-vr-2.0-software/reports/gui-dashboard-2026-10-01')
app = QApplication([])
app.setApplicationName('CephVR2.0 Dashboard')
apply_theme(app)
window = DashboardWindow(sample=True, settings=QSettings("/private/tmp/cephvr-enabled-io-review.ini", QSettings.Format.IniFormat))
controls = ReviewControls(window)
window.dashboard.output_root.setText(r"D:\CephVR\experiments\visual response study\CEPH-007\sessions\2026-10-01")
window.dashboard.log_console.setPlainText("\n".join(f"14:32:{i % 60:02}  Review message {i + 1}" for i in range(100)))
fit_window_to_screen(window)
window.show()
window.raise_()
window.activateWindow()

def confirm():
    assert window.isVisible() and window.windowHandle().screen() is not None
    window.page_buttons[1].click()
    window.devices.tabs.setCurrentIndex(1)
    panel = window.devices.microcontroller
    panel.request('Scan ports')
    QTest.qWait(150)
    assert window.grab().save(str(evidence / 'enabled-io-microcontroller.png'))
    panel.enable_controls['trial-state'].click()
    panel.enable_controls['camera-2'].click()
    app.processEvents()
    assert window.grab().save(str(evidence / 'enabled-io-disabled.png'))
    window.resize(720, 800)
    QTest.qWait(150)
    assert window.devices.tabs.widget(1).horizontalScrollBar().maximum() == 0
    assert window.grab().save(str(evidence / 'enabled-io-narrow.png'))
    status = f'PID: {os.getpid()}\nVisible: {window.isVisible()}\nTitle: {window.windowTitle()}\nSize: {window.width()}x{window.height()}\nLayout: {window.dashboard.mode}\nNative Qt window grab: enabled-io-microcontroller.png\n'
    (evidence / 'enabled-io-native-window.txt').write_text(status)
    print(status, flush=True)

close_flag = Path('/private/tmp/cephvr-dashboard-enabled-io-close.flag')
close_flag.unlink(missing_ok=True)
close_timer = QTimer()
close_timer.timeout.connect(lambda: window.close() if close_flag.exists() else None)
close_timer.start(200)
QTimer.singleShot(500, confirm)
app.exec()
with (evidence / 'enabled-io-native-window.txt').open('a') as stream:
    stream.write(f'Closed after inspection: {not window.isVisible()}\n')
print(f'Closed after inspection: {not window.isVisible()}', flush=True)
close_flag.unlink(missing_ok=True)
