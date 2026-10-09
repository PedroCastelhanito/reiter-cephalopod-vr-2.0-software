from pathlib import Path
from PyQt6.QtWidgets import QApplication
from PyQt6.QtGui import QFontDatabase
from cephvr.gui.window import DashboardWindow
from cephvr.gui.review import ReviewControls
from cephvr.gui.theme import apply_theme
app = QApplication([])
QFontDatabase.addApplicationFont("C:/Windows/Fonts/segoeui.ttf")
apply_theme(app)
window = DashboardWindow(sample=True)
controls = ReviewControls(window, simulate_projectors=True)
window.resize(900,780)
window.show()
app.processEvents()
root = Path("reports/gui-configuration-evidence-2026-10-08")
root.mkdir(exist_ok=True)
for name, page, tab in (("sidebar",0,0),("microcontroller",2,1),("spikeglx",2,3)):
    window.page_buttons[page].click()
    if page == 2:
        window.devices.tabs.setCurrentIndex(tab)
    app.processEvents()
    if name == "spikeglx":
        from PyQt6.QtTest import QTest
        QTest.qWait(40)
        app.processEvents()
        for control in (window.devices.spikeglx.config_files.load_button, window.devices.spikeglx.config_files.save_button):
            print(control.text(), control.isVisible(), control.geometry(), control.parentWidget())
    assert window.grab().save(str(root / (name + ".png")))
window.close()
