"""Capture actual configuration tabs offscreen; no device/runtime commands."""

import os
from pathlib import Path

os.environ["QT_QPA_PLATFORM"] = "offscreen"

from PyQt6.QtCore import QCoreApplication, QEvent, QSettings
from PyQt6.QtWidgets import QApplication

from cephvr.gui.protocol_batches import grouped_program
from cephvr.gui.protocol_document import review_program
from cephvr.gui.review import ReviewControls
from cephvr.gui.theme import apply_theme, load_terminal_font
from cephvr.gui.window import DashboardWindow

out = Path(__file__).parent
app = QApplication([])
apply_theme(app)
load_terminal_font()
settings = QSettings(str(out / "render-settings.ini"), QSettings.Format.IniFormat)
settings.clear()
window = DashboardWindow(sample=True, settings=settings)
ReviewControls(window)
window.protocol.editor.set_program(grouped_program(review_program()))
window.protocol.editor.enter_group()
window.resize(1920, 1032)
window.show()
window.appearance.select("amber_phosphor", persist=False)


def capture(name, widget):
    if widget is not window:
        window.appearance.crt.apply(False, scanline_alpha=0)
    for _ in range(4):
        app.processEvents()
    assert widget.grab().save(str(out / f"{name}.png"))
    window.appearance.apply_crt()


window.page_buttons[0].click()
capture("session", window.dashboard.columns[0])
window.page_buttons[1].click()
capture("protocol", window)
window.page_buttons[2].click()
for index, name in ((0, "cameras"), (1, "microcontroller"), (3, "spikeglx")):
    window.devices.tabs.setCurrentIndex(index)
    capture(name, window.devices.panels[index].columns[0])
window.devices.tabs.setCurrentIndex(2)
projectors = window.devices.projectors
for index, name in enumerate(("geometry", "calibration", "synchronization")):
    projectors.setup_tabs.setCurrentIndex(index)
    capture(name, projectors.columns[0])
window.page_buttons[3].click()
for index, name in enumerate(("preprocessing", "tracking-calibration", "pose", "motion")):
    window.tracking.tabs.setCurrentIndex(index)
    capture(name, window.tracking.columns[0])
window.resize(720, 950)
window.tracking.tabs.setCurrentIndex(1)
capture("tracking-narrow", window)
window.hide()
window.deleteLater()
QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
app.processEvents()
print("Captured 13 isolated configuration views; no runtime/device commands.")
