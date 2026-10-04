from pathlib import Path

from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication

from cephvr.gui.review import ReviewControls
from cephvr.gui.theme import apply_theme
from cephvr.gui.view import Phase, review_view
from cephvr.gui.window import DashboardWindow

target = Path('/Users/pedrocastelhanito/Dev/reiter-software/reiter-cephalopod-vr-2.0-software/reports/gui-dashboard-2026-10-01')
target.mkdir(exist_ok=True)
app = QApplication([])
apply_theme(app)
window = DashboardWindow(sample=True)
controls = ReviewControls(window)
window.show()
for name, width, height, phase in (
    ('dashboard-contextual-configuration', 1440, 940, Phase.CONFIGURATION),
    ('dashboard-contextual-running', 1440, 940, Phase.RUNNING),
    ('dashboard-contextual-narrow', 720, 800, Phase.CONFIGURATION),
):
    window.resize(width, height)
    controls.set_phase(phase)
    QTest.qWait(150)
    app.processEvents()
    assert window.grab().save(str(target / (name + '.png')))
    print(name, window.size().width(), window.size().height(), window.dashboard.mode)
controls.set_phase(Phase.RUNNING)
window.dashboard.command_buttons['Stop'].click()
QTest.qWait(150)
dialog = window.dashboard.stop_dialog
assert dialog is not None and dialog.isVisible()
assert dialog.grab().save(str(target / 'dashboard-contextual-stop-dialog.png'))
print('Stop dialog:', dialog.width(), dialog.height())
dialog.cancel.click()
window.close()
