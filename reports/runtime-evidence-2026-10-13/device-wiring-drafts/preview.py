"""Isolated device workflow review using production widgets and sample inventories."""
import sys
import tempfile
from pathlib import Path

from PyQt6.QtCore import QSettings, QTimer
from PyQt6.QtWidgets import QApplication

from cephvr.gui.review import ReviewControls
from cephvr.gui.theme import apply_theme
from cephvr.gui.window import DashboardWindow

app = QApplication([])
apply_theme(app)
temporary = tempfile.TemporaryDirectory(prefix="cephvr-wiring-review-")
settings = QSettings(str(Path(temporary.name) / "preview.ini"), QSettings.Format.IniFormat)
window = DashboardWindow(sample=True, settings=settings)
controls = ReviewControls(window, simulate_projectors=True)
cameras = window.devices.cameras
cameras.drafts[0].values.update(trigger_clock="External controller", trigger_source="Line1", trigger_frequency_hz="60")
cameras.drafts[1].enabled = False
cameras.drafts[1].values.update(trigger_clock="External controller", trigger_source="Line1", trigger_frequency_hz="30")
cameras.load_selected()
cameras.drafts_changed.emit()
window.devices.microcontroller.pin_editors["tracking"].setText("11")
window.devices.microcontroller.refresh_tests()
window.setWindowTitle("CephVR2.0 — Device wiring review · sample devices")
window.page_buttons[2].click()
window.devices.tab_bar.setCurrentIndex(0)
window.resize(1320, 940)
window.show()
window.raise_()
window.activateWindow()

def ready():
    app.processEvents()
    print(f"PREVIEW_READY visible={window.isVisible()} page=Devices devices=sample", flush=True)
    if "--live" not in sys.argv:
        directory = Path(__file__).parent
        for index, name in enumerate(("cameras", "microcontroller", "projectors")):
            window.devices.tab_bar.setCurrentIndex(index)
            app.processEvents()
            window.grab().save(str(directory / f"{name}.png"))
        window.devices.projectors.setup_tabs.setCurrentIndex(1)
        app.processEvents()
        window.grab().save(str(directory / "projector-synchronization.png"))
        for name, action in (
            ("camera-wiring", window.devices.edit_camera_wiring),
            ("projector-wiring", window.devices.edit_projector_wiring),
        ):
            def capture_dialog(name=name):
                dialog = window.devices.wiring_dialog
                if dialog is not None:
                    dialog.grab().save(str(directory / f"{name}.png"))
                    dialog.reject()
            QTimer.singleShot(100, capture_dialog)
            action()
        app.quit()

QTimer.singleShot(400, ready)
app.exec()
