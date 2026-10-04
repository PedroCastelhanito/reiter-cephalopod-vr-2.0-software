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
    ('dashboard-badges-configuration', 1440, 940, Phase.CONFIGURATION),
    ('dashboard-badges-running', 1440, 940, Phase.RUNNING),
    ('dashboard-badges-narrow', 720, 800, Phase.CONFIGURATION),
):
    window.resize(width, height)
    controls.set_phase(phase)
    QTest.qWait(150)
    app.processEvents()
    assert window.grab().save(str(target / (name + '.png')))
    print(name, window.size().width(), window.size().height(), window.dashboard.mode)
window.close()
