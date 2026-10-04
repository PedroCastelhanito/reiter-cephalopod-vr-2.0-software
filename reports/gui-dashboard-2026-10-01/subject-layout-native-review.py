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
window = DashboardWindow(sample=True, settings=QSettings("/private/tmp/cephvr-subject-layout-review.ini", QSettings.Format.IniFormat))
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
    assert window.grab().save(str(evidence / 'subject-layout-microcontroller.png'))
    window.devices.tabs.setCurrentIndex(2)
    window.devices.projectors.request('Refresh displays')
    QTest.qWait(150)
    assert window.grab().save(str(evidence / 'subject-layout-projectors.png'))
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
    projector.screen_editor.fields['Front', 'width'].setText('200')
    projector.screen_editor.fields['Front', 'height'].setText('150')
    projector.screen_editor.fields['Front', 'distance'].setText('600')
    projector.screen_editor.fields['Front', 'throw'].setText('1.2')
    for face in ('Front', 'Left', 'Right', 'Bottom'):
        for key, value in (('width', '240'), ('height', '180'), ('subject_distance', '180')):
            if key == "subject_distance":
                projector.rig_editor.screen_distances[face].setText(value)
            else:
                projector.screen_editor.fields[face, key].setText(value)
    projector.timing.pulse.click()
    projector.timing.target.setCurrentIndex(0)
    for key, value in zip(projector.timing.fields, (0, 0, 32, 32), strict=True):
        projector.timing.fields[key].setText(str(value))
    window.setWindowTitle('CephVR — explicit projector layout/geometry fixtures')
    for index, title in enumerate(('screen', 'synchronization', 'rig')):
        projector.setup_tabs.setCurrentIndex(index)
        QTest.qWait(150)
        assert window.grab().save(str(evidence / f'subject-layout-{title}.png'))
    projector.setup_tabs.setCurrentIndex(1)
    projector.timing.pulse.setChecked(False)
    QTest.qWait(150)
    window.grab().save(str(evidence / 'subject-layout-pulse-disabled.png'))
    projector.timing.pulse.setChecked(True)
    projector.setup_tabs.setCurrentIndex(2)
    QTest.qWait(150)
    assert window.grab().save(str(evidence / 'subject-layout-projector-fixtures.png'))
    projector.scrollers[0].verticalScrollBar().setValue(10000)
    QTest.qWait(150)
    window.grab().save(str(evidence / 'subject-layout-rig-bottom.png'))
    window.devices.tabs.setCurrentIndex(3)
    window.devices.spikeglx.add_input.click()
    window.devices.spikeglx.rows['custom:1'][0].setText('Aux input')
    window.devices.spikeglx.enable_controls['trial-state'].click()
    QTest.qWait(150)
    window.grab().save(str(evidence / 'subject-layout-spikeglx.png'))
    window.devices.tabs.setCurrentIndex(1)
    panel.enable_controls['trial-state'].click()
    panel.enable_controls['camera-2'].click()
    app.processEvents()
    assert window.grab().save(str(evidence / 'subject-layout-disabled.png'))
    window.resize(720, 800)
    QTest.qWait(150)
    assert window.devices.microcontroller.scrollers[0].horizontalScrollBar().maximum() == 0
    assert window.grab().save(str(evidence / 'subject-layout-narrow.png'))
    window.devices.tabs.setCurrentIndex(3)
    QTest.qWait(150)
    window.grab().save(str(evidence / 'subject-layout-spikeglx-narrow.png'))
    status = f'PID: {os.getpid()}\nVisible: {window.isVisible()}\nTitle: {window.windowTitle()}\nSize: {window.width()}x{window.height()}\nLayout: {window.dashboard.mode}\nNative Qt window grab: subject-layout-microcontroller.png\n'
    (evidence / 'subject-layout-native-window.txt').write_text(status)
    print(status, flush=True)

close_flag = Path('/private/tmp/cephvr-dashboard-subject-layout-close.flag')
close_flag.unlink(missing_ok=True)
close_timer = QTimer()
close_timer.timeout.connect(lambda: window.close() if close_flag.exists() else None)
close_timer.start(200)
QTimer.singleShot(500, confirm)
app.exec()
with (evidence / 'subject-layout-native-window.txt').open('a') as stream:
    stream.write(f'Closed after inspection: {not window.isVisible()}\n')
print(f'Closed after inspection: {not window.isVisible()}', flush=True)
close_flag.unlink(missing_ok=True)
