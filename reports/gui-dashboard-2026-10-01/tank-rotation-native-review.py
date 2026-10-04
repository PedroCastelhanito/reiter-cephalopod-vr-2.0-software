"""2026-10-04 native plot review; explicit sample dimensions, not rig measurements."""
import sys
from pathlib import Path

from PyQt6.QtCore import QPoint, QPointF, QSettings, QTimer, Qt
from PyQt6.QtGui import QMouseEvent
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication

from cephvr.gui.layouts import fit_window_to_screen
from cephvr.gui.review import ReviewControls
from cephvr.gui.theme import apply_theme
from cephvr.gui.window import DashboardWindow

app = QApplication([])
apply_theme(app)
window = DashboardWindow(sample=True, settings=QSettings('/private/tmp/cephvr-tank-rotation.ini', QSettings.Format.IniFormat))
controls = ReviewControls(window, simulate_projectors=True)
window.page_buttons[2].click()
window.devices.tabs.setCurrentIndex(2)
panel = window.devices.projectors
panel.setup_tabs.setCurrentIndex(2)
for key, value in zip(panel.rig_editor.fields, (200, 300, 150, 85, 100, 75), strict=True):
    panel.rig_editor.fields[key].setText(str(value))
for key, value in zip(panel.rig_editor.projection_fields, (1, 3000, 0.1, 0.01), strict=True):
    panel.rig_editor.projection_fields[key].setText(str(value))
for face, distance in (("Front", 125), ("Left", 110), ("Bottom", 100)):
    panel.rig_editor.screen_distances[face].setText(str(distance))
for face in ('Front', 'Left', 'Right', 'Bottom'):
    for key, value in (("width", 250 if face in ('Front', 'Bottom') else 325), ("height", 180 if face != 'Bottom' else 325), ("distance", 300), ("throw", 1.0)):
        panel.screen_editor.fields[face, key].setText(str(value))
fit_window_to_screen(window)
window.show()
window.raise_()
window.activateWindow()
root = Path('reports/gui-dashboard-2026-10-01')

def capture():
    window.grab().save(str(root / 'tank-rotation-default.png'))
    QTest.mousePress(panel.tank, Qt.MouseButton.LeftButton, pos=QPoint(60, 70))
    move = QMouseEvent(QMouseEvent.Type.MouseMove, QPointF(190, 40), QPointF(190, 40), Qt.MouseButton.NoButton, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
    QApplication.sendEvent(panel.tank, move)
    QTest.mouseRelease(panel.tank, Qt.MouseButton.LeftButton, pos=QPoint(190, 40))
    QTimer.singleShot(250, rotated)

def rotated():
    window.grab().save(str(root / 'tank-rotation-dragged.png'))
    panel.enable_controls[panel.keys[2]].click()
    QTimer.singleShot(250, subset)

def subset():
    window.grab().save(str(root / 'tank-rotation-subset.png'))
    window.resize(720, 800)
    QTimer.singleShot(250, narrow)

def narrow():
    window.grab().save(str(root / 'tank-rotation-narrow.png'))
    print(f'Captured native plot views. Rotation: {panel.tank.azimuth:g}, {panel.tank.elevation:g}.', flush=True)
    window.close()
    app.quit()

close_flag = Path('/private/tmp/cephvr-tank-rotation-close.flag')
close_flag.unlink(missing_ok=True)
close_timer = QTimer()
close_timer.timeout.connect(lambda: window.close() if close_flag.exists() else None)
close_timer.start(250)
if '--capture' in sys.argv:
    QTimer.singleShot(500, capture)
else:
    QTimer.singleShot(500, lambda: print(f'Visible: {window.isVisible()} · Devices / Projectors / Rig geometry', flush=True))
app.exec()
print(f'Closed: {not window.isVisible()}', flush=True)
close_flag.unlink(missing_ok=True)
