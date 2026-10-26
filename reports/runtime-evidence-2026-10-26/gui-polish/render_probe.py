"""Native presentation evidence with isolated settings and no backend commands."""

import json
import os
import sys
from pathlib import Path

from PyQt6.QtCore import QEvent, QSettings, Qt
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication, QMessageBox

from cephvr.gui.splash import StartupSplash
from cephvr.gui.theme import apply_theme
from cephvr.gui.window import DashboardWindow


def main() -> None:
    output = Path(sys.argv[1])
    output.mkdir(parents=True, exist_ok=True)
    app = QApplication([])
    apply_theme(app)
    records = []
    screens = [
        {
            "name": screen.name(),
            "geometry": screen.geometry().getRect(),
            "logical_dpi": screen.logicalDotsPerInch(),
            "device_pixel_ratio": screen.devicePixelRatio(),
        }
        for screen in app.screens()
    ]
    for style in ("standard", "retro_console", "amber_phosphor"):
        settings = QSettings(str(output / f"{style}.ini"), QSettings.Format.IniFormat)
        settings.setValue("appearance/style", style)
        splash = StartupSplash(settings)
        splash.begin()
        QTest.qWait(100)
        splash.pixmap().save(str(output / f"{style}-splash.png"))
        window = DashboardWindow(settings=settings)
        window.setWindowTitle("CephVR GUI polish verification — isolated")
        splash.reveal(window)
        QTest.qWait(100)
        records.append({"style": style, "maximized": window.isMaximized(),
                        "splash_closed": not splash.isVisible(),
                        "splash_timer_stopped": not splash.timer.isActive(),
                        "window_opacity": window.windowOpacity(),
                        "controller_connected": window.dashboard.view.connected})
        for index, name in enumerate(("dashboard", "protocol", "devices", "tracking")):
            window.select_page(index)
            app.processEvents()
            if name == "devices":
                for device in range(window.devices.tabs.count()):
                    window.devices.tabs.setCurrentIndex(device)
                    app.processEvents()
                    window.grab().save(str(output / f"{style}-device-{device}.png"))
            window.grab().save(str(output / f"{style}-{name}.png"))
            if style == "amber_phosphor" and name == "tracking":
                block = window.tracking.status.console.document().firstBlock()
                explicit_lines = block.text().count("\u2028") + 1
                rendered_lines = block.layout().lineCount()
                records[-1]["tracking_log_lines"] = {
                    "explicit": explicit_lines, "rendered": rendered_lines,
                }
                assert rendered_lines == explicit_lines, (
                    "Tracking log wrapped outside the message column",
                    rendered_lines, explicit_lines, block.text(),
                )
        window.select_page(0)
        console = window.dashboard.log_console
        console.clear()
        console.action_entry(("probe",), "Setup · Presentation-only diagnostic wrapping with retained timestamp and details")
        console.appendPlainText("Long diagnostic category · A later category expands retained rows without changing their identity")
        console.action_entry(("probe",), "", "Unconfirmed")
        window.grab().save(str(output / f"{style}-logs.png"))
        dialog = QMessageBox(QMessageBox.Icon.Warning, "Presentation verification",
                             "Controller unavailable", QMessageBox.StandardButton.Ok, window)
        dialog.setInformativeText("This isolated presentation probe issues no backend commands.")
        dialog.show()
        app.processEvents()
        dialog.grab().save(str(output / f"{style}-dialog.png"))
        dialog.close()
        dialog.deleteLater()
        window.tracking.annotation.close()
        window.close()
        splash.deleteLater()
        window.deleteLater()
        app.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        app.processEvents()
    (output / "results.json").write_text(json.dumps({
        "platform": app.platformName(), "scale_override": os.environ.get("QT_SCALE_FACTOR"),
        "screens": screens, "results": records,
        "scope": "Native Qt presentation only; no managed launch, controller, device or experiment operations.",
    }, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
