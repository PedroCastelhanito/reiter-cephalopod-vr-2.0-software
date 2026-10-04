from pathlib import Path
import os

from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import QApplication

from cephvr.gui.review import ReviewControls
from cephvr.gui.layouts import fit_window_to_screen
from cephvr.gui.theme import apply_theme
from cephvr.gui.window import DashboardWindow

evidence = Path('/Users/pedrocastelhanito/Dev/reiter-software/reiter-cephalopod-vr-2.0-software/reports/gui-dashboard-2026-10-01')
app = QApplication([])
app.setApplicationName('CephVR2.0 Dashboard')
apply_theme(app)
window = DashboardWindow(sample=True)
controls = ReviewControls(window)
fit_window_to_screen(window)
window.show()
window.raise_()
window.activateWindow()

def confirm():
    assert window.isVisible() and window.windowHandle().screen() is not None
    assert window.grab().save(str(evidence / 'dashboard-snap-native.png'))
    window.dashboard.show_previews()
    app.processEvents()
    assert window.dashboard.preview_dialog.grab().save(str(evidence / 'selector-snap-native.png'))
    main_frame = window.frameGeometry()
    tool_frame = window.dashboard.preview_dialog.frameGeometry()
    assert main_frame.top() == tool_frame.top(), (main_frame, tool_frame)
    print('Native frames:', main_frame.getRect(), tool_frame.getRect(), flush=True)
    status = f'PID: {os.getpid()}\nVisible: {window.isVisible()}\nTitle: {window.windowTitle()}\nSize: {window.width()}x{window.height()}\nLayout: {window.dashboard.mode}\nNative Qt window grab: dashboard-snap-native.png\n'
    (evidence / 'snap-native-window.txt').write_text(status)
    print(status, flush=True)
    window.resize(900, 800)
    app.processEvents()
    window.dashboard.show_previews()
    app.processEvents()
    main_frame = window.frameGeometry()
    tool_frame = window.dashboard.preview_dialog.frameGeometry()
    assert tool_frame.left() - main_frame.right() - 1 == 12
    assert tool_frame.top() == main_frame.top()
    assert window.grab().save(str(evidence / 'dashboard-snap-gap-native.png'))
    result = f'Gap case frames: {main_frame.getRect()} / {tool_frame.getRect()}; 12 px gap, equal top.\n'
    with (evidence / 'snap-native-window.txt').open('a') as out:
        out.write(result)
    print(result, flush=True)

close_flag = Path('/private/tmp/cephvr-dashboard-snap-close.flag')
close_flag.unlink(missing_ok=True)
close_timer = QTimer()
close_timer.timeout.connect(lambda: window.close() if close_flag.exists() else None)
close_timer.start(200)
QTimer.singleShot(500, confirm)
app.exec()
with (evidence / 'snap-native-window.txt').open('a') as stream:
    stream.write(f'Closed after inspection: {not window.isVisible()}\n')
print(f'Closed after inspection: {not window.isVisible()}', flush=True)
close_flag.unlink(missing_ok=True)
