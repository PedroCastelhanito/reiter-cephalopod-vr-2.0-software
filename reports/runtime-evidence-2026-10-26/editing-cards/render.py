"""Render actual editing groups offscreen without device connections."""

import os
from pathlib import Path

os.environ["QT_QPA_PLATFORM"] = "offscreen"

from PyQt6.QtCore import QCoreApplication, QEvent
from PyQt6.QtWidgets import QApplication, QVBoxLayout, QWidget

from cephvr.gui.batch_variation import BatchVariationRow
from cephvr.gui.cameras import CamerasPanel
from cephvr.gui.projector_calibration import CalibrationCards
from cephvr.gui.projector_geometry import FACES
from cephvr.gui.theme import PHOSPHOR_COLORS, apply_theme, load_terminal_font, phosphor_stylesheet, retro_stylesheet
from cephvr.gui.tracking_forms import TrackingForms
from cephvr.gui.variation_cards import VariationCards

app = QApplication([])
apply_theme(app)
load_terminal_font()
cameras = CamerasPanel(sample=True)
cameras.configuration.setEnabled(True)
tracking = TrackingForms()
calibration = CalibrationCards({face: {} for face in FACES})
variations = VariationCards()
for method in ("Values", "Random"):
    row = BatchVariationRow([("Front Texture", (0,), 0, "texture")], {"Front": [0]})
    row.method.setCurrentText(method)
    variations.append_rule(row)
groups = [
    ("camera", cameras.configuration, cameras.role),
    ("tracking", tracking.analysis, tracking.response.enabled),
    ("calibration", calibration, calibration.controls["Left", "offset_x_px"]),
    ("variations", variations, variations.rules[1].values),
]
hosts = []
for name, group, focus in groups:
    host = QWidget()
    hosts.append(host)
    host.setObjectName("Page")
    host.setProperty("retroConsole", True)
    host.setProperty("retroPalette", "amber_phosphor")
    host.setStyleSheet(retro_stylesheet(PHOSPHOR_COLORS) + phosphor_stylesheet())
    layout = QVBoxLayout(host)
    layout.addWidget(group)
    host.resize(600, 1)
    host.show()
    app.processEvents()
    if name == "variations":
        focus = variations.rules[1].random_fields["minimum"]
    focus.setFocus()
    app.processEvents()
    assert host.grab().save(str(Path(__file__).with_name(f"{name}.png")))
    host.hide()
for host in hosts:
    host.deleteLater()
cameras.deleteLater()
for page in (tracking.preprocessing, tracking.calibration, tracking.subject):
    page.deleteLater()
QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
app.processEvents()
print("Rendered camera, tracking, calibration and variation cards.")
