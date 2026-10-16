"""Offscreen Devices/Previews appearance evidence; simulated local fixtures only."""
from pathlib import Path
from PyQt6.QtWidgets import QApplication
from cephvr.gui.appearance import ReviewAppearance
from cephvr.gui.components import Button
from cephvr.gui.retro_instruments import blink
from cephvr.gui.review import ReviewControls
from cephvr.gui.theme import apply_theme
from cephvr.gui.window import DashboardWindow

app = QApplication([])
apply_theme(app)
window = DashboardWindow(sample=True, device_review=True)
controls = ReviewControls(window, simulate_projectors=True)
appearance = ReviewAppearance(window, window.dashboard, window.page_header, None)
appearance.select("retro_console")
root = Path(__file__).parent
window.show()
for width in (1440, 720):
    window.resize(width, 940)
    window.page_buttons[2].click()
    for index, name in enumerate(("cameras", "microcontroller", "projectors", "spikeglx")):
        window.devices.tabs.setCurrentIndex(index)
        for _ in range(5):
            app.processEvents()
        blink().timer.stop()
        blink().on = True
        window.grab().save(str(root / f"{name}-{width}.png"))
        if name == "projectors":
            projectors = window.devices.projectors
            for tab in range(projectors.setup_tabs.count()):
                projectors.setup_tabs.setCurrentIndex(tab)
                for _ in range(5):
                    app.processEvents()
                window.grab().save(str(root / f"projectors-{tab}-{width}.png"))
            projectors.setup_tabs.setCurrentIndex(0)
    window.page_buttons[0].click()
    window.dashboard.show_previews()
    for _ in range(5):
        app.processEvents()
    dialog = window.dashboard.preview_dialog
    dialog.grab().save(str(root / f"previews-{width}.png"))
    dialog.hide()
window.devices.tabs.setCurrentIndex(0)
window.page_buttons[2].click()
window.resize(1440, 940)
appearance.select("standard")
for _ in range(5):
    app.processEvents()
window.grab().save(str(root / "cameras-standard.png"))
window.hide()
window.deleteLater()
app.processEvents()
print("Device subtabs, projector pages and selector rendered at wide/narrow widths.")
