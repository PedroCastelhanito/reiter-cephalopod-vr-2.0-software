"""Bounded source-layout diagnostics; no images, device or transport activity."""

import faulthandler
import json
import os
from pathlib import Path
import threading

from PyQt6.QtCore import QSettings
from PyQt6.QtWidgets import QApplication, QSizePolicy, QWidget

from cephvr.gui.review import ReviewControls
from cephvr.gui.theme import apply_theme
from cephvr.gui.window import DashboardWindow


def expired():
    faulthandler.dump_traceback()
    os._exit(124)


watchdog = threading.Timer(15, expired)
watchdog.daemon = True
watchdog.start()
app = QApplication([])
apply_theme(app)
output = Path(__file__).parent
window = DashboardWindow(
    sample=True,
    settings=QSettings(str(output / "geometry-settings.ini"), QSettings.Format.IniFormat),
)
ReviewControls(window)
if os.environ.get("CEPHVR_GUI_PROBE_POLICIES") == "1":
    window.recordings.setSizePolicy(
        QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred
    )
    window.devices.cameras.trigger_source.setSizePolicy(
        QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed
    )
window.show()
results = []
try:
    for width in (720, 1175, 1920):
        window.resize(width, 883)
        window.select_page(2)
        window.devices.tabs.setCurrentIndex(0)
        for _ in range(5):
            app.processEvents()
        panel = window.devices.cameras
        scroll = panel.config_scroll
        viewport_width = scroll.viewport().width()
        overflow = []
        for widget in panel.columns[0].findChildren(QWidget):
            if widget.isVisible() and widget.minimumSizeHint().width() > viewport_width:
                overflow.append(
                    {
                        "class": type(widget).__name__,
                        "name": widget.objectName(),
                        "text": widget.text() if hasattr(widget, "text") else "",
                        "width": widget.width(),
                        "minimum_hint": widget.minimumSizeHint().width(),
                        "minimum": widget.minimumWidth(),
                    }
                )
        controls = {}
        for name, widget in (
            ("table", panel.table),
            ("configuration", panel.configuration),
            ("trigger_source", panel.trigger_source),
            ("rate", panel.fields["trigger_frequency_hz"]),
            ("pin", panel.trigger_pin),
        ):
            controls[name] = {
                "width": widget.width(),
                "minimum_hint": widget.minimumSizeHint().width(),
                "minimum": widget.minimumWidth(),
            }
        item = {
            "width": width,
            "stack": window.stack.width(),
            "slot": window.preview_slot.width(),
            "mode": panel.mode,
            "viewport": viewport_width,
            "left": panel.columns[0].width(),
            "horizontal_max": scroll.horizontalScrollBar().maximum(),
            "oversized_minimum_hints": overflow,
            "controls": controls,
            "combo_policy": {
                "minimum_contents": panel.trigger_source.minimumContentsLength(),
                "placeholder": panel.trigger_source.placeholderText(),
                "placeholder_pixels": panel.trigger_source.fontMetrics().horizontalAdvance(
                    panel.trigger_source.placeholderText()
                ),
                "size_adjust": panel.trigger_source.sizeAdjustPolicy().name,
            },
        }
        window.select_page(0)
        for _ in range(5):
            app.processEvents()
        item["recordings"] = [
            {
                "text": caption.text(),
                "width": caption.width(),
                "height": caption.height(),
                "required": caption.heightForWidth(caption.width()),
                "size_hint": caption.sizeHint().height(),
            }
            for caption in window.recordings.source_labels.values()
        ]
        item["recording_card"] = {
            "width": window.recordings.width(),
            "height": window.recordings.height(),
            "has_height_for_width": window.recordings.hasHeightForWidth(),
            "required": window.recordings.heightForWidth(window.recordings.width()),
            "vertical_policy": window.recordings.sizePolicy().verticalPolicy().name,
        }
        results.append(item)
    print(json.dumps(results, ensure_ascii=True, indent=2), flush=True)
finally:
    window.close()
    app.processEvents()
    watchdog.cancel()
