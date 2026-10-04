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
window = DashboardWindow(sample=True, settings=QSettings("/private/tmp/cephvr-left-tabs-review.ini", QSettings.Format.IniFormat))
controls = ReviewControls(window)
window.dashboard.output_root.setText(r"D:\CephVR\experiments\visual response study\CEPH-007\sessions\2026-10-01")
window.dashboard.log_console.setPlainText("\n".join(f"14:32:{i % 60:02}  Review message {i + 1}" for i in range(100)))
fit_window_to_screen(window)
window.show()
window.raise_()
window.activateWindow()

def confirm():
    assert window.isVisible() and window.windowHandle().screen() is not None
    assert window.grab().save(str(evidence / 'dashboard-left-tabs-native.png'))
    window.page_buttons[1].click()
    for index, name in enumerate(('cameras', 'arduino', 'projectors', 'spikeglx')):
        window.devices.tabs.setCurrentIndex(index)
        QTest.qWait(150)
        app.processEvents()
        assert window.grab().save(str(evidence / f'left-tabs-{name}.png'))
    for index, name in ((2, 'visual-stimulus'), (3, 'tracking')):
        window.page_buttons[index].click()
        QTest.qWait(150)
        window.grab().save(str(evidence / f'left-tabs-{name}.png'))
    window.page_buttons[0].click()
    controls.backend_actions["tracking"].setChecked(False)
    window.devices.cameras.enable_controls[1].click()
    window.dashboard.show_previews()
    QTest.qWait(150)
    window.dashboard.preview_dialog.grab().save(str(evidence / 'left-tabs-inactive-previews.png'))
    window.dashboard.preview_dialog.close()
    window.page_buttons[1].click()
    window.resize(720, 800)
    window.devices.tabs.setCurrentIndex(0)
    app.processEvents()
    QTest.qWait(150)
    assert window.devices.tabs.widget(0).horizontalScrollBar().maximum() == 0
    assert window.grab().save(str(evidence / 'left-tabs-narrow.png'))
    status = f'PID: {os.getpid()}\nVisible: {window.isVisible()}\nTitle: {window.windowTitle()}\nSize: {window.width()}x{window.height()}\nLayout: {window.dashboard.mode}\nNative Qt window grab: dashboard-left-tabs-native.png\n'
    (evidence / 'left-tabs-native-window.txt').write_text(status)
    print(status, flush=True)

close_flag = Path('/private/tmp/cephvr-dashboard-left-tabs-close.flag')
close_flag.unlink(missing_ok=True)
close_timer = QTimer()
close_timer.timeout.connect(lambda: window.close() if close_flag.exists() else None)
close_timer.start(200)
QTimer.singleShot(500, confirm)
app.exec()
with (evidence / 'left-tabs-native-window.txt').open('a') as stream:
    stream.write(f'Closed after inspection: {not window.isVisible()}\n')
print(f'Closed after inspection: {not window.isVisible()}', flush=True)
close_flag.unlink(missing_ok=True)
