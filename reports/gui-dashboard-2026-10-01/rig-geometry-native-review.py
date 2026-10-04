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
window = DashboardWindow(sample=True, settings=QSettings("/private/tmp/cephvr-rig-geometry-review.ini", QSettings.Format.IniFormat))
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
    assert window.grab().save(str(evidence / 'rig-geometry-microcontroller.png'))
    window.devices.tabs.setCurrentIndex(2)
    window.devices.projectors.request('Refresh displays')
    QTest.qWait(150)
    assert window.grab().save(str(evidence / 'rig-geometry-projectors.png'))
    from unittest.mock import patch
    from PyQt6.QtCore import QRect
    from cephvr.gui import projectors
    class Screen:
        def __init__(self, name, x): self.identity, self.x = name, x
        def name(self): return self.identity
        def manufacturer(self): return "Review fixture"
        def model(self): return ""
        def serialNumber(self): return ""
        def geometry(self): return QRect(self.x, 0, 1920, 1080)
        def devicePixelRatio(self): return 1
    with patch.object(projectors.QGuiApplication, 'screens', return_value=[Screen('fixture-front', 0), Screen('fixture-bottom', 1920)]), patch.object(projectors, 'windows_display_indices', return_value=({'fixture-front': '2', 'fixture-bottom': '4'}, 'Explicit review fixtures, not discovered displays')):
        window.devices.projectors.request('Refresh displays')
    projector = window.devices.projectors
    projector.projectors[projector.keys[0]].setCurrentText('Front')
    projector.projectors[projector.keys[1]].setCurrentText('Bottom')
    projector.enable_controls[projector.keys[1]].click()
    for key, value in zip(projector.rig_editor.fields, (200, 300, 150, 100, 100, 75), strict=True):
        projector.rig_editor.fields[key].setText(str(value))
    projector.screen_editor.fields['width'].setText('200')
    projector.screen_editor.fields['height'].setText('150')
    projector.screen_editor.fields['distance'].setText('600')
    projector.screen_editor.fields['throw'].setText('1.2')
    projector.timing.pulse.click()
    projector.timing.target.setCurrentIndex(0)
    projector.timing.pacing.setCurrentIndex(0)
    for key, value in zip(projector.timing.fields, (0, 0, 32, 32), strict=True):
        projector.timing.fields[key].setText(str(value))
    window.setWindowTitle('CephVR — explicit projector layout/geometry fixtures')
    for index, title in enumerate(('timing', 'rig', 'screen')):
        projector.setup_tabs.setCurrentIndex(index)
        QTest.qWait(150)
        assert window.grab().save(str(evidence / f'rig-geometry-{title}.png'))
    QTest.qWait(150)
    assert window.grab().save(str(evidence / 'rig-geometry-projector-fixtures.png'))
    window.devices.tabs.setCurrentIndex(1)
    panel.enable_controls['trial-state'].click()
    panel.enable_controls['camera-2'].click()
    app.processEvents()
    assert window.grab().save(str(evidence / 'rig-geometry-disabled.png'))
    window.resize(720, 800)
    QTest.qWait(150)
    assert window.devices.tabs.widget(1).horizontalScrollBar().maximum() == 0
    assert window.grab().save(str(evidence / 'rig-geometry-narrow.png'))
    status = f'PID: {os.getpid()}\nVisible: {window.isVisible()}\nTitle: {window.windowTitle()}\nSize: {window.width()}x{window.height()}\nLayout: {window.dashboard.mode}\nNative Qt window grab: rig-geometry-microcontroller.png\n'
    (evidence / 'rig-geometry-native-window.txt').write_text(status)
    print(status, flush=True)

close_flag = Path('/private/tmp/cephvr-dashboard-rig-geometry-close.flag')
close_flag.unlink(missing_ok=True)
close_timer = QTimer()
close_timer.timeout.connect(lambda: window.close() if close_flag.exists() else None)
close_timer.start(200)
QTimer.singleShot(500, confirm)
app.exec()
with (evidence / 'rig-geometry-native-window.txt').open('a') as stream:
    stream.write(f'Closed after inspection: {not window.isVisible()}\n')
print(f'Closed after inspection: {not window.isVisible()}', flush=True)
close_flag.unlink(missing_ok=True)
