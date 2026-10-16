"""Offscreen Devices/Previews appearance evidence; simulated local fixtures only."""
from pathlib import Path
from PyQt6.QtWidgets import QApplication
from cephvr.gui.appearance import ReviewAppearance
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

def grab_control(widget, filename):
    effects = appearance.crt_action.isChecked()
    appearance.crt_action.setChecked(False)
    app.processEvents()
    widget.grab().save(str(root / filename))
    appearance.crt_action.setChecked(effects)
    app.processEvents()

outputs = window.devices.microcontroller.signals
outputs.add()
window.devices.microcontroller.review_inputs.add()
window.devices.microcontroller.review_inputs.rows[0].name.setText("Sample input")
window.devices.microcontroller.review_inputs.rows[0].pin.setText("2")

window.show()
for width in (1440, 1175, 720):
    window.resize(width, 940)
    window.page_buttons[2].click()
    for index, name in enumerate(("cameras", "microcontroller", "projectors", "spikeglx")):
        window.devices.tabs.setCurrentIndex(index)
        for _ in range(5):
            app.processEvents()
        blink().timer.stop()
        blink().on = True
        if name == "microcontroller" and width == 1440:
            grab_control(window.devices.microcontroller.triggers, "empty-output-template.png")
            template = outputs.templates[0]
            template.pin.setText("8")
            template.selector.setCurrentIndex(template.selector.findData("behavioral"))
            outputs.add()
            for _ in range(5):
                app.processEvents()
        window.grab().save(str(root / f"{name}-{width}.png"))
        if name == "cameras":
            camera = window.devices.cameras
            grab_control(camera.configuration, f"camera-fields-{width}.png")
            grab_control(camera.table, f"camera-selection-{width}.png")
        if name == "microcontroller":
            grab_control(window.devices.microcontroller.triggers, f"outputs-{width}.png")
            grab_control(window.devices.microcontroller.io, f"inputs-{width}.png")
        if name == "projectors":
            projectors = window.devices.projectors
            for tab in range(projectors.setup_tabs.count()):
                projectors.setup_tabs.setCurrentIndex(tab)
                for _ in range(5):
                    app.processEvents()
                window.grab().save(str(root / f"projectors-{tab}-{width}.png"))
                if tab == 2:
                    projectors.timing.mode_field.grab().save(str(root / f"vsync-{width}.png"))
                    grab_control(projectors.timing, f"synchronization-{width}.png")
            projectors.setup_tabs.setCurrentIndex(0)
    window.page_buttons[0].click()
    window.dashboard.show_previews()
    for _ in range(5):
        app.processEvents()
    dialog = window.dashboard.preview_dialog
    dialog.grab().save(str(root / f"previews-{width}.png"))
    dialog.hide()
for width in (1440, 720):
    window.resize(width, 940)
    window.page_buttons[1].click()
    for _ in range(5):
        app.processEvents()
    window.grab().save(str(root / f"protocol-{width}.png"))
    window.page_buttons[3].click()
    for tab in range(window.tracking.tabs.count()):
        window.tracking.tabs.setCurrentIndex(tab)
        for _ in range(5):
            app.processEvents()
        window.grab().save(str(root / f"tracking-{tab}-{width}.png"))
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
